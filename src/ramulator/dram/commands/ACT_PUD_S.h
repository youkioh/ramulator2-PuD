#ifndef RAMULATOR_DRAM_COMMANDS_ACT_PUD_S_H
#define RAMULATOR_DRAM_COMMANDS_ACT_PUD_S_H

#include <stdexcept>

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct ACT_PUD_S {
  static constexpr DRAMCommandMeta meta = {.is_opening = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    bank->m_state = T::State::PuDSensed;
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    if (bank->m_state == T::State::PuDChargeSharing) {
      return T::Command::ACT_PUD_S;
    }
    throw std::runtime_error("[ACT_PUD_S] Invalid bank state!");
  }
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_ACT_PUD_S_H
