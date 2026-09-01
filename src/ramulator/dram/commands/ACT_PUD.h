#ifndef RAMULATOR_DRAM_COMMANDS_ACT_PUD_H
#define RAMULATOR_DRAM_COMMANDS_ACT_PUD_H

#include <stdexcept>

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct ACT_PUD {
  static constexpr DRAMCommandMeta meta = {.is_opening = true};
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    // A preserves whichever PuD phase is already active.
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    switch (bank->m_state) {
      case T::State::PuDChargeSharing:
      case T::State::PuDSensed:
        return T::Command::ACT_PUD;
      default:
        throw std::runtime_error("[ACT_PUD] Invalid bank state!");
    }
  }
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_ACT_PUD_H
