#include <stdexcept>

#include <fmt/format.h>

#include "ramulator/base/base.h"
#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/pud_sequence.h"
#include "ramulator/controller/pud_request_validation.h"
#include "ramulator/controller/refresh/i_refresh_manager.h"
#include "ramulator/controller/rowpolicy/i_row_policy.h"

namespace Ramulator {

class GenericDDRController : public ControllerBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(IController, GenericDDRController, ControllerBase, "GenericDDR")

 public:
  void init() override {
    init_base();
    RAMULATOR_PARSE_PARAM(m_pud_buffer_size, int, "pud_buffer_size").default_val(32);
    m_pud_buffer.max_size = m_pud_buffer_size;
    if (m_device.m_spec->geometry.has_subarrays()) {
      const auto& spec = *m_device.m_spec;
      m_pud_placement_levels = get_pud_placement_levels(spec);
    }
  }
  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    setup_base(frontend, memory_system);
  }
  void tick() override;

 protected:
  PuDPlacementLevels m_pud_placement_levels{};

  std::optional<bool> try_send_special_request(Request& req) override;
  bool is_pud_eligible_before_prerequisite(const Request& candidate) const;
  bool is_retained_movement_owner(const Request& req) const;
};

std::optional<bool> GenericDDRController::try_send_special_request(Request& req) {
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
  }
  return true;
}

bool GenericDDRController::is_retained_movement_owner(const Request& req) const {
  if (!is_movement_request_type(req.type_id)) {
    return false;
  }
  const size_t sequence_length = get_pud_sequence_length(req);
  if (req.occurrence_issue_history.size() != sequence_length ||
      req.occurrence_index > sequence_length) {
    throw std::logic_error(fmt::format(
        "{} has inconsistent retained ownership context: cursor {}, history {}, sequence {}",
        request_type_name(req.type_id), req.occurrence_index,
        req.occurrence_issue_history.size(), sequence_length));
  }
  return req.occurrence_index > 0 && req.occurrence_index < sequence_length &&
         req.occurrence_issue_history[0] != Request::kOccurrenceNotIssued;
}

bool GenericDDRController::is_pud_eligible_before_prerequisite(
    const Request& candidate) const {
  for (const auto& owner : m_active_buffer.buffer) {
    const bool owns_bank = is_inherited_pud_request_type(owner.type_id) ||
                           is_retained_movement_owner(owner);
    if (!owns_bank || &candidate == &owner) {
      continue;
    }

    const int owner_bank = m_device.get_flat_bank_id(owner.operands.front());
    const bool avoids_owner = m_device.for_each_target_bank_while(
        candidate.final_command, candidate.addr_vec,
        [&](int target_bank) { return target_bank != owner_bank; });
    if (!avoids_owner) {
      return false;
    }
  }
  return true;
}

void GenericDDRController::tick() {
  // Common bookkeeping: clk advance, req queue stats update, completed reads draining
  tick_prologue();

  // We give refresh requests high priority in the same tick
  m_refresh->tick();

  // Pre-schedule hooks
  m_rowpolicy->pre_schedule();  // e.g., CloseRow policy may inject PREpb here
  for (auto* p : m_plugins) {
    p->pre_schedule();
  }

  // Try to find a candidate request to schedule
  // Gate 11 priority: active > priority > oldest-ready pending PuD/read-write
  // 1. Try to schedule from active
  auto pud_eligibility = [&](const Request& req) {
    return is_pud_eligible_before_prerequisite(req);
  };
  auto movement_prerequisite_compatibility = [&](const Request& req) {
    if (is_retained_movement_owner(req) && req.command != req.final_command) {
      throw std::logic_error(fmt::format(
          "Active {} occurrence {} resolved incompatible prerequisite {} instead of {}",
          request_type_name(req.type_id), req.occurrence_index,
          m_device.m_spec->command_names[req.command],
          m_device.m_spec->command_names[req.final_command]));
    }
    return true;
  };
  Candidate cand = pick_best_ready_from(
      m_active_buffer, movement_prerequisite_compatibility, pud_eligibility);

  // 2. If no candidate found, try to schedule from priority
  if (!cand.valid) {
    cand = pick_priority_if({}, pud_eligibility);
  }

  // 3. Arbitrate the independently selected PuD and Read/Write candidates by age.
  if (!cand.valid && m_priority_buffer.size() == 0) {
    Candidate pud_cand = pick_best_ready_from(m_pud_buffer, {}, pud_eligibility);
    Candidate rw_cand = pick_rw_if({}, pud_eligibility);
    if (!pud_cand.valid) {
      cand = rw_cand;
    } else if (!rw_cand.valid || pud_cand.it->arrive <= rw_cand.it->arrive) {
      cand = pud_cand;
    } else {
      cand = rw_cand;
    }
  }

  // We have a valid request to serve this cycle
  if (cand.valid) {
    // Rowpolicy *may* upgrade the command to AutoPrecharge version
    m_rowpolicy->try_upgrade_command(*cand.it);

    if (!cand.it->is_stat_updated) {
      update_request_stats(cand.it);
    }

    // Issue command to DRAM device
    m_device.issue_command(cand.it->command, cand.it->addr_vec, m_clk);

    // Notify row policy and plugins of the issued command
    m_rowpolicy->on_issue(*cand.it);
    for (auto* p : m_plugins) {
      p->on_issue(*cand.it);
    }

    // Advance request
    if (is_pud_request_type(cand.it->type_id)) {
      const auto progress = observe_pud_command_issue(
          *cand.it, cand.it->command, m_clk, *m_device.m_spec);
      if (progress == PuDOccurrenceAdvance::Complete) {
        // Terminal PREpb ends ownership and schedulable state at issue. PuD
        // callbacks remain delayed through the accepted nRP recovery.
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

  // Post-schedule hooks
  m_rowpolicy->post_schedule();
  for (auto* p : m_plugins) {
    p->post_schedule();
  }
}

}  // namespace Ramulator
