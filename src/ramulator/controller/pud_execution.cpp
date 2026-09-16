// Shared PuD integration helpers. Existing controllers retain their tick policy.
#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/pud_request_validation.h"
#include "ramulator/controller/pud_sequence.h"
#include "ramulator/controller/rowpolicy/i_row_policy.h"

#include <algorithm>
#include <stdexcept>
#include <fmt/format.h>

namespace Ramulator {

bool ControllerBase::check_pud_request_timing(const Request& req) {
  if (is_inherited_pud_request_type(req.type_id)) {
    if (!req.pud_locations) {
      throw std::logic_error("PuD compute timing requires canonical resolved locations");
    }
    if (!req.pud_context.expired()) return check_pud_compute_issue(req);
    // Unallocated compute may only prepare conventional Bank state. Its first
    // architectural ACT requires allocation, never a scheduler-side reservation.
    return req.command >= 0 && req.command != req.final_command &&
           ControllerBase::check_request_timing(req);
  }
  if (!is_movement_request_type(req.type_id)) {
    return ControllerBase::check_request_timing(req);
  }
  if (req.pud_locations && req.command == req.final_command) {
    return check_pud_movement_issue(req);
  }
  return check_pud_occurrence_timing(req, m_clk, m_movement_timing) &&
         ControllerBase::check_request_timing(req);
}

void ControllerBase::protect_pending_pud_compute() {
  // Existing list order breaks equal-arrival ties. Sorting this transient view
  // neither reorders pending work nor introduces another admission-age field.
  std::vector<ReqBuffer::iterator> pending;
  for (auto it = m_pud_buffer.begin(); it != m_pud_buffer.end(); ++it) {
    if (!is_inherited_pud_request_type(it->type_id)) continue;
    if (!it->pud_locations) {
      throw std::logic_error("Pending PuD compute is missing canonical resolved locations");
    }
    if (it->pud_context.expired()) pending.push_back(it);
  }
  std::stable_sort(pending.begin(), pending.end(),
      [](auto a, auto b) { return a->arrive < b->arrive; });
  for (auto it : pending) {
    // Protect the complete footprint after footprint/start eligibility checks,
    // including first-command timing. Shared command-resource readiness is
    // checked at issue time.
    reserve_pud_compute(*it);
  }
}

ControllerBase::Candidate ControllerBase::pick_allocated_compute() {
  Candidate candidate;
  for (auto it = m_pud_buffer.begin(); it != m_pud_buffer.end(); ++it) {
    if (!is_inherited_pud_request_type(it->type_id)) continue;
    if (!it->pud_locations) {
      throw std::logic_error("Allocated PuD compute is missing canonical resolved locations");
    }
    if (it->pud_context.expired() || !check_pud_compute_issue(*it)) continue;
    if (!candidate.valid || it->arrive < candidate.it->arrive) {
      candidate = {true, it, &m_pud_buffer};
    }
  }
  return candidate;
}

std::optional<bool> ControllerBase::try_send_pud_request(Request& req) {
  if (!is_pud_request_type(req.type_id)) {
    return std::nullopt;
  }
  if (!m_device.m_spec->supports_controller_sequenced_request(req.type_id)) {
    throw std::runtime_error(fmt::format(
        "DRAM standard {} has an invalid PuD request mapping for {}",
        m_device.m_spec->standard_name, request_type_name(req.type_id)));
  }

  validate_pud_placement(
      req, *m_device.m_spec, m_channel_id, m_pud_placement_levels);
  initialize_pud_sequence(req, *m_device.m_spec);
  req.arrive = m_clk;
  if (!m_pud_buffer.enqueue(req)) {
    req.arrive = -1;
    return false;
  }
  if (const auto slot = legacy_pud_statistic_slot(req.type_id); slot.has_value()) {
    s_num_pud_reqs[*slot]++;
  } else if (const auto slot = movement_statistic_slot(req.type_id); slot.has_value()) {
    s_num_movement_reqs[*slot]++;
  }
  return true;
}

bool ControllerBase::is_active_movement_sequence(const Request& req) const {
  if (!is_movement_request_type(req.type_id)) {
    return false;
  }
  return describe_pud_movement_state(req).sequence_active;
}

bool ControllerBase::is_pud_candidate_eligible(
    const Request& candidate) const {
  if (!ControllerBase::is_pud_eligible_before_prerequisite(candidate)) return false;
  // Unallocated compute must also wait for existing ordinary active requests;
  // otherwise a preparatory PRE could destroy their conventional row state.
  if (is_inherited_pud_request_type(candidate.type_id)) {
    if (!candidate.pud_locations) {
      throw std::logic_error("PuD compute arbitration requires canonical resolved locations");
    }
  }
  if (is_inherited_pud_request_type(candidate.type_id) && candidate.pud_context.expired()) {
    for (const auto& active : m_active_buffer.buffer) {
      if (active.pud_locations && is_movement_request_type(active.type_id)) continue;
      if (is_inherited_pud_request_type(active.type_id)) {
        if (!active.pud_locations) {
          throw std::logic_error("Active PuD compute is missing canonical resolved locations");
        }
        continue;
      }
      if (!m_device.for_each_target_bank_while(
        candidate.final_command, candidate.addr_vec,
        [&](int bank) { return bank != m_device.get_flat_bank_id(active.addr_vec); })) return false;
    }
  }
  return true;
}

void ControllerBase::issue_pud_aware_candidate(Candidate& cand) {
  auto pud_eligibility = [&](const Request& req) {
    return is_pud_eligible_before_prerequisite(req);
  };
  const bool compute = is_inherited_pud_request_type(cand.it->type_id);
  if (compute && !cand.it->pud_locations) {
    throw std::logic_error("Selected PuD compute is missing canonical resolved locations");
  }
  const bool allocated_compute = compute && !cand.it->pud_context.expired();
  if (allocated_compute) cand.it->command = cand.it->final_command;
  // Rowpolicy *may* upgrade the command to AutoPrecharge version
  m_rowpolicy->try_upgrade_command(*cand.it);

  // Candidate state may have changed after scheduler selection. Revalidate
  // ownership eligibility and any active-close protection used by its
  // selection path, then require the selected command to remain the current
  // prerequisite and timing-ready.
  bool still_eligible = pud_eligibility(*cand.it);
  const bool selected_with_active_close_protection =
      cand.buffer == &m_priority_buffer || cand.buffer == &m_read_buffer ||
      cand.buffer == &m_write_buffer;
  if (still_eligible && selected_with_active_close_protection &&
      would_close_active(*cand.it)) {
    still_eligible = false;
  }
  bool ready_to_issue = false;
  if (still_eligible) {
    if (is_active_movement_sequence(*cand.it) &&
        cand.it->command != cand.it->final_command) {
      throw std::logic_error(fmt::format(
          "Active {} occurrence {} became incompatible before issue: {} instead of {}",
          request_type_name(cand.it->type_id), cand.it->occurrence_index,
          m_device.m_spec->command_names[cand.it->command],
          m_device.m_spec->command_names[cand.it->final_command]));
    }
    if (allocated_compute) {
      ready_to_issue = cand.it->command == cand.it->final_command && check_pud_compute_issue(*cand.it);
    } else if (compute) {
      // A preparatory PRE owns no compute resources and advances no occurrence.
      ready_to_issue = cand.it->command != cand.it->final_command &&
          !m_device.conflicts_with_protected_pud(cand.it->command, cand.it->addr_vec) &&
          cand.it->command == get_preq_command(cand.it->final_command, cand.it->addr_vec) &&
          check_request_timing(*cand.it);
    } else if (is_movement_request_type(cand.it->type_id) && cand.it->pud_locations &&
               cand.it->command == cand.it->final_command) {
      ready_to_issue = get_preq_command(*cand.it) == cand.it->command && check_request_timing(*cand.it);
    } else {
      ready_to_issue = validate_request_for_issue(*cand.it);
    }
  }

  if (still_eligible && ready_to_issue && !cand.it->is_stat_updated) {
    update_request_stats(cand.it);
  }

  if (still_eligible && ready_to_issue) {
    // Issue command to DRAM device
    // Range dispatch advances the sole Request internally. Preserve only a
    // transient pre-issue view for existing row-policy/plugin notifications.
    std::optional<Request> pud_issued;
    if (allocated_compute) {
      pud_issued = *cand.it;
      issue_pud_compute(*cand.it);
    } else if (is_movement_request_type(cand.it->type_id) && cand.it->pud_locations &&
               cand.it->command == cand.it->final_command) {
      pud_issued = *cand.it;
      issue_pud_movement(*cand.it);
    } else {
      m_device.issue_command(cand.it->command, cand.it->addr_vec, m_clk);
    }

    // Notify row policy and plugins of the issued command
    const auto& issued = pud_issued ? *pud_issued : *cand.it;
    m_rowpolicy->on_issue(issued);
    for (auto* p : m_plugins) {
      p->on_issue(issued);
    }

    // Advance request
    if (allocated_compute) {
      if (cand.it->occurrence_index == get_pud_sequence_length(*cand.it)) {
        // Keep the physical footprint protected until delayed recovery departure.
        retire_request(cand.it, *cand.buffer);
      }
    } else if (pud_issued) {
      if (cand.it->occurrence_index == get_pud_sequence_length(*cand.it)) {
        retire_request(cand.it, *cand.buffer);
      } else if (cand.buffer != &m_active_buffer) {
        promote_to_active(cand.it, *cand.buffer);
      }
    } else if (is_pud_request_type(cand.it->type_id)) {
      const auto progress = observe_pud_command_issue(
          *cand.it, cand.it->command, m_clk, *m_device.m_spec);
      if (progress == PuDOccurrenceAdvance::Complete) {
        // Only preparatory commands use this observation path. Canonical
        // movement/compute issue advances its Request in Device dispatch.
        retire_request(cand.it, *cand.buffer);
      } else if (progress == PuDOccurrenceAdvance::Advanced &&
                 cand.buffer != &m_active_buffer) {
        promote_to_active(cand.it, *cand.buffer);
      }
    } else if (cand.it->command == cand.it->final_command) {
      retire_request(cand.it, *cand.buffer);
    } else if (m_device.m_spec->command_meta[cand.it->command].is_opening) {
      promote_to_active(cand.it, *cand.buffer);
    }
  }
}

}  // namespace Ramulator
