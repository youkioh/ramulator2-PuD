#ifndef RAMULATOR_DRAM_COMMANDS_RD_MOV_H
#define RAMULATOR_DRAM_COMMANDS_RD_MOV_H

#include <stdexcept>

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct RD_MOV {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    if (bank->m_state != T::State::MovementActive) {
      throw std::runtime_error("[RD_MOV] Invalid bank state!");
    }
    bank->m_state = T::State::MovementDataValid;
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    if (bank->m_state != T::State::MovementActive) {
      throw std::runtime_error("[RD_MOV] Invalid bank state!");
    }
    return T::Command::RD_MOV;
  }
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_RD_MOV_H
