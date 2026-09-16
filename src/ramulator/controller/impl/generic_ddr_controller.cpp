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
      set_location_resolver(pud_binding(*m_device.m_spec).placement(
          placement_profile, *m_device.m_spec, m_addr_mapper->m_impl->get_name()));
    }
  }
  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    setup_base(frontend, memory_system);
  }
  void tick() override;
  bool check_request_timing(const Request& req) override {
    return check_pud_request_timing(req);
  }

 protected:
  // One control-unit pool per controller/channel, shared across Banks/Ranks.
  // Occupancy and range ownership are derived from m_protected_pud.
  int m_pud_compute_engines = 8;
  std::optional<bool> try_send_special_request(Request& req) override {
    return try_send_pud_request(req);
  }
  bool supports_range_aware_compute() const override {
    return m_device.m_spec->supports_compute_requests();
  }
  bool is_pud_eligible_before_prerequisite(const Request& candidate) const override {
    return is_pud_candidate_eligible(candidate);
  }
};

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
  allocate_pud_compute(m_pud_compute_engines);

  // Try to find a candidate request to schedule
  // Gate 11 priority: active > priority > oldest-ready pending PuD/read-write
  // 1. Try to schedule from active
  auto pud_eligibility = [&](const Request& req) {
    return is_pud_eligible_before_prerequisite(req);
  };
  auto movement_prerequisite_compatibility = [&](const Request& req) {
    if (is_active_movement_sequence(req) && req.command != req.final_command) {
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
          return is_active_movement_sequence(req) && pud_eligibility(req);
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
      return req.pud_context.expired() &&
             !m_device.conflicts_with_protected_pud(req.final_command, req.addr_vec);
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

  // The controller chooses the slot/candidate; common integration owns issue,
  // notifications and PuD progression through delayed recovery.
  if (cand.valid) issue_pud_aware_candidate(cand);

  // Post-schedule hooks
  m_rowpolicy->post_schedule();
  for (auto* p : m_plugins) {
    p->post_schedule();
  }
}

}  // namespace Ramulator
