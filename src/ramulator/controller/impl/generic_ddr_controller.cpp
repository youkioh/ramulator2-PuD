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
    if (m_config.is_map() && m_config.map().contains("pud_compute_engines")) {
      throw std::runtime_error("pud_compute_engines has been removed: finite PuD control-engine capacity is not modeled; remove this parameter");
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
      m_pud_placement_profile = placement_profile;
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
  protect_pending_pud_compute();

  Candidate cand = pick_pud_aware_candidate();

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
