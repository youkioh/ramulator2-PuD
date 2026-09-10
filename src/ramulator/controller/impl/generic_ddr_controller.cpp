#include <algorithm>
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
    RAMULATOR_PARSE_PARAM(m_pud_compute_engines, int, "pud_compute_engines").default_val(8);
    if (m_pud_compute_engines <= 0) {
      throw std::runtime_error("pud_compute_engines must be positive");
    }
    if (m_device.m_spec->geometry.has_subarrays()) {
      const auto& spec = *m_device.m_spec;
      m_pud_placement_levels = get_pud_placement_levels(spec);
    }
    if (m_device.m_spec->supports_movement_requests()) {
      m_movement_timing = make_movement_timing_constraints(*m_device.m_spec);
    }
    std::string placement_profile;
    RAMULATOR_PARSE_PARAM(placement_profile, std::string, "pud_placement_profile").default_val("");
    if (!placement_profile.empty()) {
      if (placement_profile != "MIMDRAM_DDR4_8Gb_x8_v1" ||
          !supports_range_aware_compute() || !supports_movement_requests()) {
        throw std::runtime_error("Unsupported PuD placement profile or incomplete unified-substrate capability");
      }
      set_location_resolver(std::make_shared<PuD::LocationResolver>(
          PuD::PlacementProfile::mimdram_ddr4_8gb_x8_v1(), *m_device.m_spec,
          PuD::MappingContext{"physical", 1, "CacheLineInterleave",
                              m_addr_mapper->m_impl->get_name(), false, 0}));
    }
  }
  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    setup_base(frontend, memory_system);
  }
  void tick() override;
  bool check_request_timing(const Request& req) override;

 protected:
  PuDPlacementLevels m_pud_placement_levels{};
  PuDMovementTimingConstraints m_movement_timing{};
  // One control-unit pool per controller/channel, shared across Banks/Ranks.
  // Occupancy and range ownership are derived from m_protected_compute.
  int m_pud_compute_engines = 8;
  void allocate_pud_compute();
  Candidate pick_allocated_compute();

  std::optional<bool> try_send_special_request(Request& req) override;
  bool supports_range_aware_compute() const override {
    return m_device.m_spec->supports_compute_requests();
  }
  bool is_pud_eligible_before_prerequisite(const Request& candidate) const override;
  bool is_retained_movement_owner(const Request& req) const;
};

bool GenericDDRController::check_request_timing(const Request& req) {
  if (is_inherited_pud_request_type(req.type_id)) {
    if (!req.pud_locations) {
      throw std::logic_error("PuD compute timing requires canonical resolved locations");
    }
    if (!req.pud_compute_context.expired()) return check_pud_compute_issue(req);
    // Unallocated compute may only prepare conventional Bank state. Its first
    // architectural ACT requires allocation, never a scheduler-side reservation.
    return req.command >= 0 && req.command != req.final_command &&
           ControllerBase::check_request_timing(req);
  }
  if (!is_movement_request_type(req.type_id)) {
    return ControllerBase::check_request_timing(req);
  }
  return check_pud_occurrence_timing(req, m_clk, m_movement_timing) &&
         ControllerBase::check_request_timing(req);
}

void GenericDDRController::allocate_pud_compute() {
  // Existing list order breaks equal-arrival ties. Sorting this transient view
  // neither reorders pending work nor introduces another admission-age field.
  std::vector<ReqBuffer::iterator> pending;
  for (auto it = m_pud_buffer.begin(); it != m_pud_buffer.end(); ++it) {
    if (!is_inherited_pud_request_type(it->type_id)) continue;
    if (!it->pud_locations) {
      throw std::logic_error("Pending PuD compute is missing canonical resolved locations");
    }
    if (it->pud_compute_context.expired()) pending.push_back(it);
  }
  std::stable_sort(pending.begin(), pending.end(),
      [](auto a, auto b) { return a->arrive < b->arrive; });
  for (auto it : pending) {
    int engine = 0;
    for (; engine < m_pud_compute_engines; ++engine) {
      if (std::none_of(m_protected_compute.begin(), m_protected_compute.end(),
          [&](const auto& held) { return held.engine == engine; })) break;
    }
    if (engine == m_pud_compute_engines) break;
    // Commit engine + complete range together after conflict eligibility. No
    // first-ACT local timing or shared command readiness participates here.
    reserve_pud_compute(*it, engine);
  }
}

ControllerBase::Candidate GenericDDRController::pick_allocated_compute() {
  Candidate candidate;
  for (auto it = m_pud_buffer.begin(); it != m_pud_buffer.end(); ++it) {
    if (!is_inherited_pud_request_type(it->type_id)) continue;
    if (!it->pud_locations) {
      throw std::logic_error("Allocated PuD compute is missing canonical resolved locations");
    }
    if (it->pud_compute_context.expired() || !check_pud_compute_issue(*it)) continue;
    if (!candidate.valid || it->arrive < candidate.it->arrive) {
      candidate = {true, it, &m_pud_buffer};
    }
  }
  return candidate;
}

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
  } else if (const auto slot = movement_statistic_slot(req.type_id); slot.has_value()) {
    s_num_movement_reqs[*slot]++;
  }
  return true;
}

bool GenericDDRController::is_retained_movement_owner(const Request& req) const {
  if (!is_movement_request_type(req.type_id)) {
    return false;
  }
  return describe_pud_movement_state(req).owns_bank;
}

bool GenericDDRController::is_pud_eligible_before_prerequisite(
    const Request& candidate) const {
  if (!ControllerBase::is_pud_eligible_before_prerequisite(candidate)) return false;
  auto avoids_bank = [&](int owner_bank) {
    const auto avoids_command = [&](int command) {
      return m_device.for_each_target_bank_while(
          command, candidate.addr_vec,
          [&](int target_bank) { return target_bank != owner_bank; });
    };
    return avoids_command(candidate.final_command) &&
           (candidate.command < 0 || avoids_command(candidate.command));
  };
  // A failed active-buffer promotion retains the movement owner in its original
  // buffer. Compute ownership instead lives in protected range records.
  for (const auto* buffer : {&m_active_buffer, &m_pud_buffer}) {
    for (const auto& owner : buffer->buffer) {
      if (!is_retained_movement_owner(owner) || &candidate == &owner) continue;
      if (!avoids_bank(m_device.get_flat_bank_id(owner.operands.front()))) return false;
    }
  }
  // Terminal PRE retires movement ownership, but independent commands cannot
  // reuse or close its Bank until the existing delayed recovery has completed.
  for (const auto& recovering : m_pending) {
    if (is_movement_request_type(recovering.type_id) && recovering.depart > m_clk &&
        !avoids_bank(m_device.get_flat_bank_id(recovering.operands.front()))) return false;
  }
  // Unallocated compute must also wait for existing ordinary active requests;
  // otherwise a preparatory PRE could destroy their conventional row state.
  if (is_inherited_pud_request_type(candidate.type_id)) {
    if (!candidate.pud_locations) {
      throw std::logic_error("PuD compute arbitration requires canonical resolved locations");
    }
  }
  if (is_inherited_pud_request_type(candidate.type_id) && candidate.pud_compute_context.expired()) {
    for (const auto& active : m_active_buffer.buffer) {
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

  // Completion release precedes refresh/hooks; queued maintenance therefore
  // stops new allocations in this tick while existing allocations can drain.
  allocate_pud_compute();

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
  if (!cand.valid) {
    // Promotion backpressure cannot turn an acquired movement into unowned
    // pending work or let priority maintenance strand its continuation.
    cand = pick_best_ready_from(m_pud_buffer, movement_prerequisite_compatibility,
        [&](const Request& req) {
          return is_retained_movement_owner(req) && pud_eligibility(req);
        });
  }
  // Allocated compute has active-continuation precedence regardless of first
  // ACT or active-buffer capacity. A blocked context leaves issue available.
  auto compute_cand = pick_allocated_compute();
  if (compute_cand.valid && (!cand.valid || compute_cand.it->arrive < cand.it->arrive)) {
    cand = compute_cand;
  }

  // 2. If no candidate found, try to schedule from priority
  if (!cand.valid) {
    cand = pick_priority_if({}, pud_eligibility);
  }

  // 3. Arbitrate the independently selected PuD and Read/Write candidates by age.
  if (!cand.valid && m_priority_buffer.size() == 0) {
    Candidate pud_cand = pick_best_ready_from(m_pud_buffer, {}, [&](const Request& req) {
      if (!pud_eligibility(req)) return false;
      if (!is_inherited_pud_request_type(req.type_id)) return true;
      if (!req.pud_locations) {
        throw std::logic_error("Pending PuD compute is missing canonical resolved locations");
      }
      // Only conventional preparation reaches the generic prerequisite path.
      // Allocated compute uses its explicit occurrence; it never repairs a Bank.
      return req.pud_compute_context.expired() &&
             !m_device.conflicts_with_protected_compute(req.final_command, req.addr_vec);
    });
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
    const bool compute = is_inherited_pud_request_type(cand.it->type_id);
    if (compute && !cand.it->pud_locations) {
      throw std::logic_error("Selected PuD compute is missing canonical resolved locations");
    }
    const bool allocated_compute = compute && !cand.it->pud_compute_context.expired();
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
      if (is_retained_movement_owner(*cand.it) &&
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
            !m_device.conflicts_with_protected_compute(cand.it->command, cand.it->addr_vec) &&
            cand.it->command == get_preq_command(cand.it->final_command, cand.it->addr_vec) &&
            check_request_timing(*cand.it);
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
      std::optional<Request> compute_issued;
      if (allocated_compute) {
        compute_issued = *cand.it;
        issue_pud_compute(*cand.it);
      } else {
        m_device.issue_command(cand.it->command, cand.it->addr_vec, m_clk);
      }

      // Notify row policy and plugins of the issued command
      const auto& issued = compute_issued ? *compute_issued : *cand.it;
      m_rowpolicy->on_issue(issued);
      for (auto* p : m_plugins) {
        p->on_issue(issued);
      }

      // Advance request
      if (allocated_compute) {
        if (cand.it->occurrence_index == get_pud_sequence_length(*cand.it)) {
          // Keep engine + range protected until delayed recovery departure.
          retire_request(cand.it, *cand.buffer);
        }
      } else if (is_pud_request_type(cand.it->type_id)) {
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
  }

  // Post-schedule hooks
  m_rowpolicy->post_schedule();
  for (auto* p : m_plugins) {
    p->post_schedule();
  }
}

}  // namespace Ramulator
