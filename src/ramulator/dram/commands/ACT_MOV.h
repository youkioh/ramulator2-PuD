#ifndef RAMULATOR_DRAM_COMMANDS_ACT_MOV_H
#define RAMULATOR_DRAM_COMMANDS_ACT_MOV_H

#include <stdexcept>

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct ACT_MOV {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    switch (bank->m_state) {
      case T::State::Closed:
        bank->m_state = T::State::MovementActive;
        bank->m_row_state.clear();
        return;
      case T::State::MovementActive:
      case T::State::MovementDataValid:
        return;
      default:
        throw std::runtime_error("[ACT_MOV] Invalid bank state!");
    }
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    switch (bank->m_state) {
      case T::State::Closed:
      case T::State::MovementActive:
      case T::State::MovementDataValid:
        return T::Command::ACT_MOV;
      case T::State::Opened:
        return T::Command::PREpb;
      default:
        throw std::runtime_error("[ACT_MOV] Invalid bank state!");
    }
  }
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_ACT_MOV_H
