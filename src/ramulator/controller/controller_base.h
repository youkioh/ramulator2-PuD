#ifndef RAMULATOR_CONTROLLER_CONTROLLER_BASE_H
#define RAMULATOR_CONTROLLER_CONTROLLER_BASE_H

#include <array>
#include <cstdint>
#include <deque>
#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

#include "ramulator/controller/addr_mapper/i_addr_mapper.h"
#include "ramulator/controller/i_controller.h"
#include "ramulator/controller/plugin/i_controller_plugin.h"
#include "ramulator/controller/scheduler/i_scheduler.h"
#include "ramulator/dram/device.h"
#include "ramulator/controller/pud_request_validation.h"
#include "ramulator/controller/pud_sequence.h"

class LocatedSystemUnderTest;
class ControllerUnderTestCpp;

namespace Ramulator {

class IRefreshManager;
class IRowPolicy;
class IFrontEnd;
class IMemorySystem;
class PuDConflictUnderTest;

/*
 * Unified public GenericDRAM -> GenericDDR admission -> existing PuD buffer.
 * m_pud_buffer: pending PuD + allocated compute Requests (sole schedulable copies)
 *                    |
 *       compute: oldest-to-newest first fit, complete physical footprint
 *       movement: first ACT acquires footprint
 *                    |
 *                    v
 *        +----------------------------------+
 *        | ControllerBase::ProtectedPuD | <-- YOU ARE HERE
 *        +----------------+-----------------+
 *                         | owns lifetime
 *                         v
 *                +-------------------+
 * Request -weak->| PuDExecutionContext |<-weak- Device registry
 *                +-------------------+       (conflict visibility)
 *                         |
 *         terminal PRE -> recovery -> release -> completion/callback
 *               |
 *               v
 *        Request moves to m_pending; protection outlives command scheduling.
 *
 * Request owns sequence/history; context (device.h) owns protocol phase.
 * Delayed completion uses the binding's recovery anchor/interval and releases
 * protection before accounting/callback (DDR4: terminal timestamp + nRP).
 * Protected records retain resource identity/lifetime via explicit reservations.
 * PuD issue --> Device consumes the current resolved occurrence (device.h).
 * GenericDDR checks physical footprint conflicts against this store.
 * Allocation derives from the Request/context association. Ready allocated
 * compute uses GenericDDR's narrow candidate path; no active-buffer ownership,
 * separate allocated-request container or allocator range table.
 */

// Shared infrastructure for all DRAM controller implementations.
// Provides buffers, stats, sub-component management, and low-level scheduling
// helpers. Subclasses own their tick() policy and protocol-specific behavior.
class ControllerBase : public IController, public Implementation {
 public:
  DRAMDevice m_device;
  IAddrMapper* m_addr_mapper = nullptr;

  // Forwarding methods — bind m_clk for sub-components
  bool check_timing(int command, const AddrVec_t& addr_vec);
  virtual bool check_request_timing(const Request& req);
  virtual bool is_pud_eligible_before_prerequisite(const Request& req) const;
  bool validate_request_for_issue(const Request& req);
  int get_preq_command(int command, const AddrVec_t& addr_vec);
  int get_preq_command(const Request& req);

  // IController overrides
  void set_channel_id(int channel_id) override;
  int get_tx_bytes() const override;
  int get_num_levels() const override;
  float get_tCK() const override;
  bool supports_compute_requests() const override;
  bool supports_movement_requests() const override;
  std::shared_ptr<const PuD::LocationResolver> location_resolver() const override { return m_location_resolver; }
  // Install the shared placement authority before traffic; canonical public
  // execution also requires the combined standard capability.
  void set_location_resolver(std::shared_ptr<const PuD::LocationResolver> resolver);

  bool send(Request& req) override;
  bool priority_send(Request& req) override;

  const ReqBuffer& pending_pud_requests() const { return m_pud_buffer; }

  void update_stats() override;
  void finalize() override;
  void reset_stats() override;

 protected:
  friend class PuDConflictUnderTest;
  friend class ::LocatedSystemUnderTest;
  friend class ::ControllerUnderTestCpp;
  ControllerBase(const ConfigNode& config, Implementation* parent)
      : Implementation(config, "controller", "ControllerBase", parent) {
  }

  // Shared initialization — call from subclass init()
  void init_base();

  // Shared stats registration — call from subclass setup()
  void setup_base(IFrontEnd* frontend, IMemorySystem* memory_system);

  // Optional derived-controller ingress handling. A value means the request
  // was handled; nullopt continues through the generic Read/Write path.
  virtual std::optional<bool> try_send_special_request(Request& req) {
    return std::nullopt;
  }
  virtual bool supports_range_aware_compute() const { return false; }

  // Sub-components
  IScheduler* m_scheduler = nullptr;
  IRefreshManager* m_refresh = nullptr;
  IRowPolicy* m_rowpolicy = nullptr;
  std::vector<IControllerPlugin*> m_plugins;
  std::shared_ptr<const PuD::LocationResolver> m_location_resolver;

  // Request buffers
  std::deque<Request> m_pending;
  ReqBuffer m_active_buffer;
  ReqBuffer m_priority_buffer;
  ReqBuffer m_read_buffer;
  ReqBuffer m_write_buffer;
  ReqBuffer m_pud_buffer;
  // Efficiently tracks addresses of buffered write requests for write-forwarding
  std::unordered_set<Addr_t> m_buffered_write_addrs;

  // Buffer config
  int m_read_buffer_size;
  int m_write_buffer_size;
  int m_priority_buffer_size;
  int m_pud_buffer_size = 32;
  float m_wr_low_watermark;
  float m_wr_high_watermark;
  bool m_is_write_mode = false;

  // Cached spec lookups
  int m_bank_level = -1;
  int m_tCK_ps = -1;

  // Per flat-bank count of requests in m_active_buffer (typically 0 or 1).
  // Maintained by promote_to_active / retire_request.
  std::vector<int> m_active_per_bank;

  // Physical PuD invocation lifetime, from acquisition through terminal recovery.
  // Neither this store nor the context owns a cursor or duplicates mat geometry.
  struct ProtectedPuD {
    std::shared_ptr<PuDExecutionContext> context;
    bool completion_pending = false;
  };
  std::vector<ProtectedPuD> m_protected_pud;
  bool reserve_pud_compute(Request& req);
  bool pud_compute_resources_available(const Request& req) const;
  bool pud_compute_start_eligible(const Request& req) const;
  PuDExecutionContext& protected_pud_context(const Request& req) const;
  ProtectedPuD& protected_pud_record(const Request& req);
  void release_completed_resources(Request& req);

  // Issue mechanics for protected contexts; movement acquires at first ACT.
  // These methods do not select/schedule pending work.
  bool check_pud_compute_issue(const Request& req);
  void issue_pud_compute(Request& req);
  bool check_pud_movement_issue(const Request& req);
  void issue_pud_movement(Request& req);

  // Opt-in PuD integration; conventional controllers keep their existing tick.
  PuDPlacementLevels m_pud_placement_levels{};
  PuDMovementTimingConstraints m_movement_timing{};
  bool check_pud_request_timing(const Request& req);
  std::optional<bool> try_send_pud_request(Request& req);
  bool is_pud_candidate_eligible(const Request& req) const;
  bool is_active_movement_sequence(const Request& req) const;
  void protect_pending_pud_compute();

  // Stats
  Clk_t m_measured_clk = 0;

  size_t s_row_hits = 0;
  size_t s_row_misses = 0;
  size_t s_row_conflicts = 0;
  size_t s_read_row_hits = 0;
  size_t s_read_row_misses = 0;
  size_t s_read_row_conflicts = 0;
  size_t s_write_row_hits = 0;
  size_t s_write_row_misses = 0;
  size_t s_write_row_conflicts = 0;

  size_t m_num_cores = 0;
  std::vector<size_t> s_read_row_hits_per_core;
  std::vector<size_t> s_read_row_misses_per_core;
  std::vector<size_t> s_read_row_conflicts_per_core;

  size_t s_num_read_reqs = 0;
  size_t s_num_write_reqs = 0;
  size_t s_num_maintenance_reqs = 0;
  size_t s_num_read_reqs_served = 0;
  size_t s_num_write_reqs_served = 0;
  size_t s_num_maintenance_reqs_served = 0;
  size_t s_num_read_reqs_forwarded = 0;
  size_t s_num_write_reqs_coalesced = 0;
  size_t s_queue_len = 0;
  size_t s_read_queue_len = 0;
  size_t s_write_queue_len = 0;
  size_t s_priority_queue_len = 0;
  size_t s_pud_queue_len = 0;
  float s_queue_len_avg = 0;
  float s_read_queue_len_avg = 0;
  float s_write_queue_len_avg = 0;
  float s_priority_queue_len_avg = 0;
  float s_pud_queue_len_avg = 0;

  size_t s_read_latency = 0;
  float s_avg_read_latency = 0;

  std::array<size_t, kNumLegacyPuDStatisticSlots> s_num_pud_reqs{};
  std::array<size_t, kNumLegacyPuDStatisticSlots> s_num_pud_reqs_completed{};
  std::array<size_t, kNumLegacyPuDStatisticSlots> s_pud_latency{};
  std::array<float, kNumLegacyPuDStatisticSlots> s_avg_pud_latency{};

  std::array<size_t, kNumMovementStatisticSlots> s_num_movement_reqs{};
  std::array<size_t, kNumMovementStatisticSlots> s_num_movement_reqs_completed{};
  std::array<size_t, kNumMovementStatisticSlots> s_movement_latency{};
  std::array<float, kNumMovementStatisticSlots> s_avg_movement_latency{};
  std::array<std::uint64_t, kNumMovementStatisticSlots> s_movement_moved_bits{};

  float s_read_throughput_MBps = 0;
  float s_write_throughput_MBps = 0;
  float s_total_throughput_MBps = 0;

  // Common tick preamble: advance clock, accumulate queue stats,
  // drain completed requests.
  void tick_prologue();

  // Final command done — move delayed completions to pending or remove immediately.
  void retire_request(ReqBuffer::iterator& req_it, ReqBuffer& buffer);

  // Opening command done — move request from source buffer to active buffer.
  void promote_to_active(ReqBuffer::iterator& req_it, ReqBuffer& buffer);

  // ── Systematic scheduling ──────────────────────────────────────────
  // Controllers use this helper to ask the scheduler for the best request
  // from a specific buffer under an optional eligibility filter.

  struct Candidate {
    bool valid = false;
    ReqBuffer::iterator it;
    ReqBuffer* buffer = nullptr;
  };

  Candidate pick_allocated_compute();
  // After the controller grants a command slot. Preserves pre-issue views for
  // notifications, then retires/promotes the sole authoritative Request.
  void issue_pud_aware_candidate(Candidate& candidate);

  Candidate pick_best_ready_from(
      ReqBuffer& buffer,
      RequestFilterRef command_filter = {},
      RequestFilterRef eligibility_filter = {});
  Candidate pick_priority_if(
      RequestFilterRef command_filter = {},
      RequestFilterRef eligibility_filter = {});
  Candidate pick_rw_if(
      RequestFilterRef command_filter = {},
      RequestFilterRef eligibility_filter = {});

  // Scheduling helpers
  bool would_close_active(const Request& req) const;
  void update_request_stats(ReqBuffer::iterator& req);
  void serve_completed_requests();
  void set_write_mode();
};

}  // namespace Ramulator

#endif  // RAMULATOR_CONTROLLER_CONTROLLER_BASE_H
