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

void DRAMDevice::protect_pud_compute(const std::shared_ptr<PuDComputeContext>& context) {
  if (!context || context->m_device != this) {
    throw std::logic_error("Cannot protect foreign compute context");
  }
  std::erase_if(m_protected_compute, [](const auto& held) { return held.expired(); });
  m_protected_compute.push_back(context);
}

bool DRAMDevice::conflicts_with_protected_compute(int command, const AddrVec_t& addr_vec) const {
  for (const auto& held : m_protected_compute) {
    const auto context = held.lock();
    if (!context) continue;
    const int bank = get_flat_bank_id(context->locations()->operands.front().external);
    if (!for_each_target_bank_while(command, addr_vec,
          [&](int target) { return target != bank; })) return true;
  }
  return false;
}

std::unique_ptr<PuDComputeContext> DRAMDevice::make_pud_compute_context(const Request& req) const {
  if (m_spec->standard_name != "DDR4_PuD_Movement" || !req.pud_locations ||
      !is_inherited_pud_request_type(req.type_id)) {
    throw std::logic_error("Range context requires a located combined-substrate compute request");
  }
  validate_pud_placement(req, *m_spec, m_root->m_node_id, get_pud_placement_levels(*m_spec));
  if (req.occurrence_index != 0 || req.occurrence_issue_history.size() != get_pud_sequence_length(req)) {
    throw std::logic_error("Range context requires an initialized, unissued Request sequence");
  }
  auto context = std::unique_ptr<PuDComputeContext>(new PuDComputeContext(this, req.pud_locations));
  validate_pud_command(req, describe_pud_occurrence(req, 0, *m_spec), context.get());
  return context;
}

void DRAMDevice::validate_pud_command(const Request& req, const PuDOccurrence& occurrence,
                                      const PuDComputeContext* context) const {
  if (!context || context->m_device != this || !req.pud_locations ||
      req.pud_locations != context->m_locations || occurrence.locations != context->m_locations ||
      !is_inherited_pud_request_type(req.type_id)) {
    throw std::logic_error("Wrong or unassociated compute range context");
  }
  const auto expected = describe_pud_occurrence(req, req.occurrence_index, *m_spec);
  if (occurrence.index != expected.index || occurrence.command != expected.command ||
      occurrence.operand_index != expected.operand_index || occurrence.role != expected.role ||
      occurrence.terminal != expected.terminal || req.final_command != expected.command ||
      req.addr_vec != expected.location()->external) {
    throw std::logic_error("Wrong or stale compute occurrence context");
  }
  if (req.occurrence_issue_history.size() != get_pud_sequence_length(req)) {
    throw std::logic_error("Inconsistent compute occurrence history");
  }
  Clk_t last = Request::kOccurrenceNotIssued;
  for (size_t i = 0; i < req.occurrence_issue_history.size(); ++i) {
    const auto issued = req.occurrence_issue_history[i];
    if (i < req.occurrence_index) {
      if (issued <= last) {
        throw std::logic_error("Missing or unordered compute occurrence history");
      }
      last = issued;
    } else if (issued != Request::kOccurrenceNotIssued) {
      throw std::logic_error("Premature compute occurrence history");
    }
  }

  using Phase = PuDComputeContext::Phase;
  const auto phase = context->m_phase;
  const auto& command = m_spec->command_names[expected.command];
  bool legal = false;
  if (command == "ACT_PUD_OC" || command == "ACT_PUD_S_OC") {
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
    throw std::logic_error("Incompatible compute range phase");
  }
  // Ordinary preparation is separate from architectural range dispatch. This
  // seam never converts a range occurrence to a Bank-wide prerequisite PRE.
  const auto* bank = m_bank_nodes[get_flat_bank_id(expected.location()->external)];
  if (bank->m_state != m_spec->get_state_id("Closed") || !bank->m_row_state.empty()) {
    throw std::logic_error("Compute range requires drained conventional Bank state");
  }
}

bool DRAMDevice::check_pud_timing(const Request& req, const PuDOccurrence& occurrence,
                                 const PuDComputeContext* context, Clk_t clk) {
  validate_pud_command(req, occurrence, context);
  return check_pud_compute_occurrence_timing(req, clk, *m_spec) &&
         m_root->check_timing(occurrence.command, occurrence.location()->external, clk);
}

void DRAMDevice::issue_pud_command(Request& req, const PuDOccurrence& occurrence,
                                  PuDComputeContext* context, Clk_t clk) {
  if (!check_pud_timing(req, occurrence, context, clk)) {
    throw std::logic_error("Compute range timing not ready");
  }
  // Outgoing edge inventory (DDR4_PuD + DDR4_PuD_Movement Python definitions):
  // - Channel: retain any explicit shared constraints. The existing controller
  //   serializes one-CK C/A issue; Python omits Device bus edges for one tick.
  // - Bank ACT_PUD*/N -> compute/PRE: PRADA phases, interpreted only by the
  //   Request-local timing helper above; no Bank history/deadline update here.
  // - Terminal PRE -> ACT/compute/ACT_MOV (Bank), -> REFab (Rank): recovery
  //   belongs to this range. Protected records enforce whole-scope exclusion, not a shared
  //   deadline from this PRE. No conventional Bank/Rank state is closed here.
  // Incoming conventional PREpb/PREab/RDA/WRA/REFab edges are still checked by
  // the complete hierarchy. Ordinary commands keep their full update path,
  // including nRRD/nFAW; compute ACTs enter neither activation-current history.
  // No command-cycle/transport adjustment or second local timing graph.
  m_root->update_timing(occurrence.command, occurrence.location()->external, clk, false);
  const auto& command = m_spec->command_names[occurrence.command];
  using Phase = PuDComputeContext::Phase;
  if (occurrence.terminal) {
    // Recovery time is recorded by the terminal Request occurrence below;
    // Controller retirement derives depart and retains protection until then.
    context->m_phase = Phase::Recovering;
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

void DRAMDevice::issue_command(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  validate_command(command, addr_vec, clk);
  m_root->update_timing(command, addr_vec, clk);
  apply_action(command, addr_vec, clk);
}

bool DRAMDevice::check_timing(int command, const AddrVec_t& addr_vec, Clk_t clk) {
  return m_root->check_timing(command, addr_vec, clk);
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
  // or hierarchical timing update. Range dispatch has its own explicit seam.
  if (conflicts_with_protected_compute(command, addr_vec)) {
    throw std::logic_error("Command conflicts with protected compute context");
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
