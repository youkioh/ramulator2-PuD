#include "ramulator/dram/device.h"

#include "ramulator/controller/pud_request_validation.h"
#include "ramulator/controller/pud_sequence.h"

namespace Ramulator {

void DRAMDevice::init(std::unique_ptr<DRAMSpec> spec) {
  m_spec_owner = std::move(spec);
  m_spec = m_spec_owner.get();
  m_bank_level = m_spec->get_level_id("Bank");
  m_root = std::make_unique<DRAMNode>(m_spec, nullptr, 0, 0);
  m_root->for_each_at_level(m_bank_level, [&](DRAMNode* bank) { m_bank_nodes.push_back(bank); });
}

void DRAMDevice::set_channel_id(int channel_id) {
  m_root->m_node_id = channel_id;
}

void DRAMDevice::protect_pud(const std::shared_ptr<PuDExecutionContext>& context) {
  if (!context || context->m_device != this) {
    throw std::logic_error("Cannot protect foreign PuD invocation context");
  }
  std::erase_if(m_protected_pud, [](const auto& held) { return held.expired(); });
  m_protected_pud.push_back(context);
}

bool DRAMDevice::conflicts_with_protected_pud(int command, const AddrVec_t& addr_vec) const {
  for (const auto& held : m_protected_pud) {
    const auto context = held.lock();
    if (!context) continue;
    const int bank = get_flat_bank_id(context->locations()->operands.front().external);
    if (!for_each_target_bank_while(command, addr_vec,
          [&](int target) { return target != bank; })) return true;
  }
  return false;
}

std::unique_ptr<PuDExecutionContext> DRAMDevice::make_pud_context(const Request& req) const {
  if (!m_spec->supports_compute_requests() || !req.pud_locations ||
      !is_pud_request_type(req.type_id)) {
    throw std::logic_error("PuD invocation context requires a located PuD request on a compute-capable Device");
  }
  validate_pud_placement(req, *m_spec, m_root->m_node_id, get_pud_placement_levels(*m_spec));
  if (req.occurrence_index != 0 || req.occurrence_issue_history.size() != get_pud_sequence_length(req)) {
    throw std::logic_error("PuD invocation context requires an initialized, unissued Request sequence");
  }
  auto context = std::unique_ptr<PuDExecutionContext>(new PuDExecutionContext(this, req.pud_locations));
  validate_pud_command(req, describe_pud_occurrence(req, 0, *m_spec), context.get());
  return context;
}

bool DRAMDevice::conflicts_with_protected_pud(const Request& req) const {
  for (const auto& held : m_protected_pud) {
    const auto context = held.lock();
    if (!context || context == req.pud_context.lock()) continue;
    if (req.pud_locations->conflicts(*context->locations())) return true;
  }
  return false;
}

void DRAMDevice::validate_pud_command(const Request& req, const PuDOccurrence& occurrence,
                                      const PuDExecutionContext* context) const {
  if (!context || context->m_device != this || !req.pud_locations ||
      req.pud_locations != context->m_locations || occurrence.locations != context->m_locations ||
      !is_pud_request_type(req.type_id)) {
    throw std::logic_error("Wrong or unassociated PuD invocation context");
  }
  const auto expected = describe_pud_occurrence(req, req.occurrence_index, *m_spec);
  if (occurrence.index != expected.index || occurrence.command != expected.command ||
      occurrence.operand_index != expected.operand_index || occurrence.role != expected.role ||
      occurrence.terminal != expected.terminal || req.final_command != expected.command ||
      req.addr_vec != expected.location()->external) {
    throw std::logic_error("Wrong or stale PuD occurrence context");
  }
  if (req.occurrence_issue_history.size() != get_pud_sequence_length(req)) {
    throw std::logic_error("Inconsistent PuD occurrence history");
  }
  Clk_t last = Request::kOccurrenceNotIssued;
  for (size_t i = 0; i < req.occurrence_issue_history.size(); ++i) {
    const auto issued = req.occurrence_issue_history[i];
    if (i < req.occurrence_index) {
      if (issued <= last) {
        throw std::logic_error("Missing or unordered PuD occurrence history");
      }
      last = issued;
    } else if (issued != Request::kOccurrenceNotIssued) {
      throw std::logic_error("Premature PuD occurrence history");
    }
  }

  using Phase = PuDExecutionContext::Phase;
  const auto phase = context->m_phase;
  const auto& command = m_spec->command_names[expected.command];
  bool legal = false;
  if (is_movement_request_type(req.type_id)) {
    const auto state = describe_pud_movement_state(req);
    const auto expected_phase = !state.sequence_active ? Phase::Closed :
        (state.source_valid ? Phase::MovementDataValid : Phase::MovementActive);
    legal = phase == expected_phase;
  } else if (command == "ACT_PUD_OC" || command == "ACT_PUD_S_OC") {
    legal = expected.index == 0 && phase == Phase::Closed;
  } else if (command == "ACT_PUD") {
    legal = phase == Phase::ChargeSharing || phase == Phase::Sensed;
  } else if (command == "ACT_PUD_S") {
    legal = phase == Phase::ChargeSharing;
  } else if (command == "N") {
    legal = phase == Phase::Sensed;
  } else if (command == "PREpb") {
    legal = expected.terminal && phase == Phase::Sensed;
  }
  if (!legal) {
    throw std::logic_error("Incompatible PuD invocation phase");
  }
  // Ordinary preparation is separate from architectural PuD dispatch. This
  // seam never converts an invocation occurrence to a Bank-wide prerequisite PRE.
  const auto* bank = m_bank_nodes[get_flat_bank_id(expected.location()->external)];
  if (bank->m_state != m_spec->get_state_id("Closed") || !bank->m_row_state.empty()) {
    throw std::logic_error("PuD invocation requires drained conventional Bank state");
  }
}

bool DRAMDevice::check_pud_timing(const Request& req, const PuDOccurrence& occurrence,
                                 const PuDExecutionContext* context, Clk_t clk) {
  // An unissued movement may probe without acquiring protection. Actual issue
  // below always requires the controller's committed reservation.
  if (!is_movement_request_type(req.type_id) || req.occurrence_index != 0 ||
      !req.pud_context.expired()) validate_pud_reservation(req, context);
  validate_pud_command(req, occurrence, context);
  return clk >= m_pud_ca_ready && clk >= m_command_ca_ready &&
         (!is_movement_request_type(req.type_id) ||
          check_pud_occurrence_timing(req, clk, make_movement_timing_constraints(*m_spec))) &&
         check_pud_local_timing(req, clk, *m_spec) &&
         m_root->check_timing(occurrence.command, occurrence.location()->external, clk);
}

void DRAMDevice::issue_pud_command(Request& req, const PuDOccurrence& occurrence,
                                  PuDExecutionContext* context, Clk_t clk) {
  validate_pud_reservation(req, context);
  if (!check_pud_timing(req, occurrence, context, clk)) {
    throw std::logic_error("PuD invocation timing not ready");
  }
  // Outgoing edge inventory (DDR4_PuD + DDR4_PuD_Movement Python definitions):
  // - Channel: retain explicit shared constraints and actual command occupancy.
  // - Bank ACT_MOV -> WR_MOV/PRE and PRE -> ACT_MOV: invocation-local
  //   movement history, alongside the occurrence-specific LC/GB edges.
  // - Bank ACT_PUD*/N -> compute/PRE: PRADA phases, interpreted only by the
  //   Request-local timing helper above; no Bank history/deadline update here.
  // - Terminal PRE -> ACT/compute/ACT_MOV (Bank), -> REFab (Rank): recovery
  //   belongs to this invocation. Protected records enforce footprint conflicts
  //   and ordinary/maintenance scopes, not a shared deadline from this PRE.
  //   No conventional Bank/Rank state is closed here.
  // Incoming conventional PREpb/PREab/RDA/WRA/REFab edges are still checked by
  // the complete hierarchy. Ordinary commands keep their full update path,
  // including nRRD/nFAW; PuD ACTs enter neither activation-current history.
  // The current occurrence supplies the resolved row and MatRange together via
  // its validated immutable location/context association. The issued Request
  // prefix retains activated operand identity; no selected-range shadow exists.
  m_root->update_timing(occurrence.command, occurrence.location()->external, clk, false);
  m_pud_ca_ready = clk + m_spec->command_cycles.at(occurrence.command);
  const auto& command = m_spec->command_names[occurrence.command];
  using Phase = PuDExecutionContext::Phase;
  if (occurrence.terminal) {
    // Recovery time is recorded by the terminal Request occurrence below;
    // Controller retirement derives depart and retains protection until then.
    context->m_phase = Phase::Recovering;
  } else if (is_movement_request_type(req.type_id)) {
    if (command == "RD_MOV") context->m_phase = Phase::MovementDataValid;
    else if (command == "WR_MOV" || occurrence.index == 0) context->m_phase = Phase::MovementActive;
    // LC source PRE and destination ACT retain source-valid HFF metadata.
  } else if (command != "N") {
    if (command == "ACT_PUD_OC") {
      context->m_phase = Phase::ChargeSharing;
    } else if (command == "ACT_PUD_S" || command == "ACT_PUD_S_OC") {
      context->m_phase = Phase::Sensed;
    }
  }
  // Commit the existing sole Request cursor/history together with the action.
  // Callers must not observe the same occurrence again after this seam returns.
  observe_pud_command_issue(req, occurrence.command, clk, *m_spec);
}

void DRAMDevice::validate_pud_reservation(const Request& req, const PuDExecutionContext* context) const {
  if (!context || req.pud_context.lock().get() != context) {
    throw std::logic_error("PuD issue requires an associated invocation context");
  }
  for (const auto& held : m_protected_pud) {
    if (held.lock().get() == context) return;
  }
  throw std::logic_error("PuD issue requires protected PuD invocation context");
}

void DRAMDevice::issue_command(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  validate_command(command, addr_vec, clk);
  if (clk < m_pud_ca_ready) throw std::logic_error("C/A occupied by PuD command");
  m_root->update_timing(command, addr_vec, clk);
  apply_action(command, addr_vec, clk);
  // PuD invocation dispatch must respect the current raw command cycle.
  // Conventional timing and dual/multi-cycle bus generation retain their behavior.
  m_command_ca_ready = clk + m_spec->command_cycles.at(command);
}

bool DRAMDevice::check_timing(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  return clk >= m_pud_ca_ready && m_root->check_timing(command, addr_vec, clk);
}

int DRAMDevice::get_preq_command(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  validate_command(command, addr_vec, clk);
  auto preq_fn = m_spec->funcs.preqs[command];
  if (!preq_fn) return command;

  int resolved = command;
  for_each_target_bank_while(command, addr_vec, [&](int flat_bank_id) {
    int preq = preq_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
    if (preq != command) { resolved = preq; return false; }
    return true;
  });
  return resolved;
}

bool DRAMDevice::check_rowbuffer_hit(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  auto rowhit_fn = m_spec->funcs.rowhits[command];
  if (!rowhit_fn) {
    return false;
  }
  int flat_bank_id = get_flat_bank_id(addr_vec);
  return rowhit_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
}

bool DRAMDevice::check_node_open(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  auto rowopen_fn = m_spec->funcs.rowopens[command];
  if (!rowopen_fn) {
    return false;
  }
  int flat_bank_id = get_flat_bank_id(addr_vec);
  return rowopen_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
}

int DRAMDevice::get_flat_bank_id(const AddrVec_t& addr_vec) const {
  int id = 0;
  for (int lvl = 1; lvl <= m_bank_level; lvl++) {
    id = id * m_spec->organization.level_sizes[lvl] + addr_vec[lvl];
  }
  return id;
}

bool DRAMDevice::bank_matches(DRAMNode* bank, const AddrVec_t& addr_vec) {
  for (auto* n = bank; n != nullptr; n = n->m_parent_node) {
    if (addr_vec[n->m_level] != -1 && addr_vec[n->m_level] != n->m_node_id) {
      return false;
    }
  }
  return true;
}

std::vector<int> DRAMDevice::get_target_banks(int command, const AddrVec_t& addr_vec) const {
  std::vector<int> ids;
  for_each_target_bank(command, addr_vec, [&](int id) { ids.push_back(id); });
  return ids;
}

void DRAMDevice::validate_command(int command, const AddrVec_t& addr_vec, Clk_t clk) const {
  // Validate the whole scope before even the first Bank prerequisite/action
  // or hierarchical timing update. PuD dispatch has its own explicit seam.
  if (conflicts_with_protected_pud(command, addr_vec)) {
    throw std::logic_error("Command conflicts with protected PuD invocation context");
  }
  auto validate_fn = m_spec->funcs.validators[command];
  if (!validate_fn) return;
  for_each_target_bank(command, addr_vec, [&](int flat_bank_id) {
    validate_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
  });
}

void DRAMDevice::apply_action(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  auto action_fn = m_spec->funcs.actions[command];
  if (!action_fn) return;
  for_each_target_bank(command, addr_vec, [&](int flat_bank_id) {
    action_fn(m_bank_nodes[flat_bank_id], command, addr_vec, clk);
  });
}

}  // namespace Ramulator
