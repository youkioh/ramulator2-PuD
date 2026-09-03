#include <stdexcept>

#include <fmt/format.h>

#include "ramulator/base/base.h"
#include "ramulator/controller/controller_base.h"
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
      m_pud_rank_level = spec.get_level_id("Rank");
      m_pud_bankgroup_level = spec.get_level_id("BankGroup");
      m_pud_bank_level = spec.get_level_id("Bank");
      m_pud_row_level = spec.get_level_id("Row");
      m_cmd_prepb = spec.get_command_id("PREpb");
      m_cmd_act_pud = spec.get_command_id("ACT_PUD");
      m_cmd_act_pud_oc = spec.get_command_id("ACT_PUD_OC");
      m_cmd_act_pud_s = spec.get_command_id("ACT_PUD_S");
      m_cmd_act_pud_s_oc = spec.get_command_id("ACT_PUD_S_OC");
      m_cmd_n = spec.get_command_id("N");
    }
  }
  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    setup_base(frontend, memory_system);
  }
  void tick() override;

 protected:
  int m_pud_rank_level = -1;
  int m_pud_bankgroup_level = -1;
  int m_pud_bank_level = -1;
  int m_pud_row_level = -1;
  int m_cmd_prepb = -1;
  int m_cmd_act_pud = -1;
  int m_cmd_act_pud_oc = -1;
  int m_cmd_act_pud_s = -1;
  int m_cmd_act_pud_s_oc = -1;
  int m_cmd_n = -1;

  std::optional<bool> try_send_special_request(Request& req) override;
  void validate_pud_placement(const Request& req) const;
  void configure_pud_step(Request& req) const;
  bool advance_pud_sequence(Request& req) const;
  bool is_pud_eligible_before_prerequisite(const Request& candidate) const;
};

std::optional<bool> GenericDDRController::try_send_special_request(Request& req) {
  if (!is_inherited_pud_request_type(req.type_id)) {
    return std::nullopt;
  }
  if (!m_device.m_spec->supports_controller_sequenced_request(req.type_id)) {
    throw std::runtime_error(fmt::format(
        "DRAM standard {} has an invalid PuD request mapping for {}",
        m_device.m_spec->standard_name, request_type_name(req.type_id)));
  }

  validate_pud_placement(req);
  req.pud_sequence_index = 0;
  configure_pud_step(req);
  req.arrive = m_clk;
  if (!m_pud_buffer.enqueue(req)) {
    req.arrive = -1;
    return false;
  }
  s_num_pud_reqs[*legacy_pud_statistic_slot(req.type_id)]++;
  return true;
}

void GenericDDRController::configure_pud_step(Request& req) const {
  const size_t step = req.pud_sequence_index;
  const size_t operand_count = req.operands.size();
  const size_t sequence_length = req.type_id == Request::Type::NOT ? 3 : operand_count + 1;
  if (step >= sequence_length) {
    throw std::logic_error(fmt::format(
        "{} sequence step {} is outside [0, {})",
        request_type_name(req.type_id), step, sequence_length));
  }

  int next_command = -1;
  if (step + 1 == sequence_length) {
    next_command = m_cmd_prepb;
    // PREpb is bank-scoped; retain the preceding operand address.
  } else if (req.type_id == Request::Type::RowCopy) {
    next_command = step == 0 ? m_cmd_act_pud_s_oc : m_cmd_act_pud;
    req.addr_vec = req.operands[step];
  } else if (req.type_id == Request::Type::MAJ3 || req.type_id == Request::Type::MAJ5) {
    if (step == 0) {
      next_command = m_cmd_act_pud_oc;
    } else if (step + 1 == operand_count) {
      next_command = m_cmd_act_pud_s;
    } else {
      next_command = m_cmd_act_pud;
    }
    req.addr_vec = req.operands[step];
  } else if (req.type_id == Request::Type::NOT) {
    next_command = step == 0 ? m_cmd_act_pud_s_oc : m_cmd_n;
    req.addr_vec = req.operands[0];
  } else {
    throw std::logic_error(fmt::format(
        "Cannot configure PuD sequence for request type {}", req.type_id));
  }

  req.command = -1;
  req.final_command = next_command;
}

bool GenericDDRController::advance_pud_sequence(Request& req) const {
  req.pud_sequence_index++;
  const size_t sequence_length =
      req.type_id == Request::Type::NOT ? 3 : req.operands.size() + 1;
  if (req.pud_sequence_index == sequence_length) {
    return true;
  }
  configure_pud_step(req);
  return false;
}

bool GenericDDRController::is_pud_eligible_before_prerequisite(
    const Request& candidate) const {
  for (const auto& owner : m_active_buffer.buffer) {
    if (!is_inherited_pud_request_type(owner.type_id) || &candidate == &owner) {
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

void GenericDDRController::validate_pud_placement(const Request& req) const {
  const auto& spec = *m_device.m_spec;
  if (!spec.geometry.has_subarrays()) {
    throw std::runtime_error(fmt::format(
        "DRAM standard {} does not define PuD subarray geometry", spec.standard_name));
  }
  if (req.operands.empty()) {
    throw std::runtime_error(fmt::format(
        "{} request has no operands", request_type_name(req.type_id)));
  }

  auto validate_operand = [&](const AddrVec_t& operand, size_t operand_idx) {
    if (operand.size() != static_cast<size_t>(spec.level_count)) {
      throw std::runtime_error(fmt::format(
          "{} operand {} has {} hierarchy coordinates; expected {}",
          request_type_name(req.type_id), operand_idx, operand.size(), spec.level_count));
    }
    for (int level = 0; level < spec.level_count; level++) {
      int value = operand[level];
      if (level == 0) {
        if (value != m_channel_id) {
          throw std::runtime_error(fmt::format(
              "{} operand {} targets channel {}, but controller owns channel {}",
              request_type_name(req.type_id), operand_idx, value, m_channel_id));
        }
      } else if (value < 0 || value >= spec.organization.level_sizes[level]) {
        throw std::runtime_error(fmt::format(
            "{} operand {} coordinate {} at level {} is outside [0, {})",
            request_type_name(req.type_id), operand_idx, value,
            spec.level_names[level], spec.organization.level_sizes[level]));
      }
    }
  };

  validate_operand(req.operands[0], 0);
  const auto& first = req.operands[0];
  const int first_subarray = spec.geometry.subarray_id(first[m_pud_row_level]);

  for (size_t i = 1; i < req.operands.size(); i++) {
    const auto& operand = req.operands[i];
    validate_operand(operand, i);
    for (int level : {m_pud_rank_level, m_pud_bankgroup_level, m_pud_bank_level}) {
      if (operand[level] != first[level]) {
        throw std::runtime_error(fmt::format(
            "{} operands must share {}: operand 0 has {}, operand {} has {}",
            request_type_name(req.type_id), spec.level_names[level],
            first[level], i, operand[level]));
      }
    }
    int subarray = spec.geometry.subarray_id(operand[m_pud_row_level]);
    if (subarray != first_subarray) {
      throw std::runtime_error(fmt::format(
          "{} operands must share a logical subarray: operand 0 has {}, operand {} has {}",
          request_type_name(req.type_id), first_subarray, i, subarray));
    }
  }
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
  Candidate cand = pick_best_ready_from(m_active_buffer, {}, pud_eligibility);

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
    if (is_inherited_pud_request_type(cand.it->type_id) &&
        cand.it->command == cand.it->final_command) {
      const bool complete = advance_pud_sequence(*cand.it);
      if (complete) {
        retire_request(cand.it, *cand.buffer);
      } else if (cand.buffer != &m_active_buffer) {
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
