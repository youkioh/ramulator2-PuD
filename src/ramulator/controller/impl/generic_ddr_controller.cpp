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
    if (m_device.m_spec->geometry.has_subarrays()) {
      const auto& spec = *m_device.m_spec;
      m_pud_rank_level = spec.get_level_id("Rank");
      m_pud_bankgroup_level = spec.get_level_id("BankGroup");
      m_pud_bank_level = spec.get_level_id("Bank");
      m_pud_row_level = spec.get_level_id("Row");
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

  std::optional<bool> try_send_special_request(Request& req) override;
  void validate_pud_placement(const Request& req) const;
};

std::optional<bool> GenericDDRController::try_send_special_request(Request& req) {
  if (!is_pud_request_type(req.type_id)) {
    return std::nullopt;
  }
  if (m_device.m_spec->supported_requests[req.type_id] != DRAMSpec::CONTROLLER_SEQUENCED) {
    throw std::runtime_error(fmt::format(
        "DRAM standard {} has an invalid PuD request mapping for {}",
        m_device.m_spec->standard_name, request_type_name(req.type_id)));
  }

  validate_pud_placement(req);
  req.addr_vec = req.operands.front();
  req.arrive = m_clk;
  if (!m_pud_buffer.enqueue(req)) {
    req.arrive = -1;
    return false;
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
  // Priority: active > priority > read/write
  // 1. Try to schedule from active
  Candidate cand = pick_best_ready_from(m_active_buffer, {});

  // 2. If no candidate found, try to schedule from priority
  if (!cand.valid) {
    cand = pick_priority_if();
  }

  // 3. If no candidate found, try to schedule from read/write (with write mode check)
  if (!cand.valid && m_priority_buffer.size() == 0) {
    cand = pick_rw_if();
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
    if (cand.it->command == cand.it->final_command) {
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
