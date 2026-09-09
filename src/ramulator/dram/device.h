#ifndef RAMULATOR_DRAM_DEVICE_H
#define RAMULATOR_DRAM_DEVICE_H

#include <memory>
#include <vector>

#include "ramulator/base/config_node.h"
#include "ramulator/base/type.h"
#include "ramulator/dram/dram_spec.h"
#include "ramulator/dram/node.h"

namespace Ramulator {

struct PuDOccurrence;
class DRAMDevice;

// One explicit temporal record per lockstep compute invocation, never per mat.
// The retained W2 bundle identifies the invocation across Request copies. The
// Request remains the sole owner of primitive/order/cursor and issue history.
class PuDComputeContext {
 public:
  enum class Phase { Closed, ChargeSharing, Sensed, Recovering };
  Phase phase() const { return m_phase; }
  const auto& locations() const { return m_locations; }
  const auto& activated_operands() const { return m_activated_operands; }
  Clk_t last_issue_clk() const { return m_last_issue_clk; }
  Clk_t recovery_ready_clk() const { return m_recovery_ready_clk; }
  bool recovery_ready(Clk_t clk) const {
    return m_phase == Phase::Recovering && clk >= m_recovery_ready_clk;
  }
  PuDComputeContext(const PuDComputeContext&) = delete;
  PuDComputeContext& operator=(const PuDComputeContext&) = delete;

 private:
  friend class DRAMDevice;
  PuDComputeContext(const DRAMDevice* device, std::shared_ptr<const PuD::RequestLocations> locations)
      : m_device(device), m_locations(std::move(locations)) {}
  const DRAMDevice* m_device;
  std::shared_ptr<const PuD::RequestLocations> m_locations;
  Phase m_phase = Phase::Closed;
  std::vector<size_t> m_activated_operands;
  // Temporal consistency stamp, not another cursor or timing-edge scoreboard.
  Clk_t m_last_issue_clk = Request::kOccurrenceNotIssued;
  Clk_t m_recovery_ready_clk = -1;
};

/**
 * @brief    DRAM Device — owns the DRAMSpec, node tree, and flat bank array.
 *
 * Provides all device-level operations: command issue (timing + state),
 * prerequisite checks, row buffer queries. The controller delegates here
 * for anything that touches DRAM state or timing.
 *
 * All operations take Clk_t clk as a parameter — the device is stateless
 * with respect to simulation time. The controller owns the clock.
 */
class DRAMDevice {
 public:
  std::unique_ptr<DRAMSpec> m_spec_owner;  // Owns the polymorphic spec
  DRAMSpec* m_spec = nullptr;              // Non-owning pointer for convenient access
  std::unique_ptr<DRAMNode> m_root;        // Hierarchical node tree (for timing)
  std::vector<DRAMNode*> m_bank_nodes;     // Flat bank view (non-owning, for state dispatch)
  int m_bank_level = -1;                   // Cached level ID for "Bank" (hot-path use)

  void init(std::unique_ptr<DRAMSpec> spec);
  void set_channel_id(int channel_id);

  // Issue a command: update timing (hierarchical) then apply state (flat bank dispatch)
  void issue_command(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Timing-only check — hierarchical (walks node tree)
  bool check_timing(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Internal W3 component seam. Callers establish range protection separately;
  // this creates no engine/allocation, transport or completion ownership. Public
  // v2 submission remains disabled. Descriptors are checked against the current
  // Request before any timing/action; a null, foreign or stale context fails.
  std::unique_ptr<PuDComputeContext> make_pud_compute_context(const Request& req) const;
  bool check_pud_timing(const Request& req, const PuDOccurrence& occurrence,
                        const PuDComputeContext* context, Clk_t clk);
  void issue_pud_command(Request& req, const PuDOccurrence& occurrence,
                         PuDComputeContext* context, Clk_t clk);

  // Non-owning visibility of controller reservations, including pre-ACT and
  // recovery. Controller release remains the sole lifetime authority.
  void protect_pud_compute(const std::shared_ptr<PuDComputeContext>& context);
  bool conflicts_with_protected_compute(int command, const AddrVec_t& addr_vec) const;

  // Prerequisite check — flat bank dispatch
  int get_preq_command(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Row buffer hit check — flat bank lookup (always single bank)
  bool check_rowbuffer_hit(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Row open check — flat bank lookup (always single bank)
  bool check_node_open(int command, const AddrVec_t& addr_vec, Clk_t clk);

  // Compute flat bank index from addr_vec
  int get_flat_bank_id(const AddrVec_t& addr_vec) const;

  // Check if a bank node matches an addr_vec pattern (wildcards are -1)
  static bool bank_matches(DRAMNode* bank, const AddrVec_t& addr_vec);

  // Get indices into m_bank_nodes for the target banks of a command (cold-path wrapper)
  std::vector<int> get_target_banks(int command, const AddrVec_t& addr_vec) const;

  /// Visit target bank(s) for a command with early-exit support.
  /// Visitor signature: bool(int bank_id) — return true to continue, false to stop.
  /// Returns true if all banks were visited, false if visitor short-circuited.
  template <class Visitor>
  bool for_each_target_bank_while(int command, const AddrVec_t& addr_vec, Visitor&& visitor) const {
    switch (m_spec->bank_targets[command]) {
      case BankTarget::Single:
        return visitor(get_flat_bank_id(addr_vec));

      case BankTarget::All:
        for (int i = 0; i < static_cast<int>(m_bank_nodes.size()); ++i) {
          if (!bank_matches(m_bank_nodes[i], addr_vec)) continue;
          if (!visitor(i)) return false;
        }
        return true;

      case BankTarget::SameBank: {
        const int target_bank_id = addr_vec[m_bank_level];
        for (int i = 0; i < static_cast<int>(m_bank_nodes.size()); ++i) {
          if (m_bank_nodes[i]->m_node_id != target_bank_id) continue;
          if (!bank_matches(m_bank_nodes[i], addr_vec)) continue;
          if (!visitor(i)) return false;
        }
        return true;
      }
    }
    return true;
  }

  /// Visit all target bank(s) for a command. Visitor signature: void(int bank_id).
  template <class Visitor>
  void for_each_target_bank(int command, const AddrVec_t& addr_vec, Visitor&& visitor) const {
    for_each_target_bank_while(command, addr_vec, [&](int bank_id) {
      visitor(bank_id);
      return true;
    });
  }

 private:
  std::vector<std::weak_ptr<PuDComputeContext>> m_protected_compute;
  void validate_pud_command(const Request& req, const PuDOccurrence& occurrence,
                            const PuDComputeContext* context) const;
  // Run any command-specific defensive validation across the complete target
  // scope before prerequisite resolution, timing mutation, or state mutation.
  void validate_command(int command, const AddrVec_t& addr_vec, Clk_t clk) const;

  // Flat bank dispatch — apply action to target banks
  void apply_action(int command, const AddrVec_t& addr_vec, Clk_t clk);
};

}  // namespace Ramulator

#endif  // RAMULATOR_DRAM_DEVICE_H
