#include "ramulator/controller/controller_base.h"

#include <algorithm>
#include <stdexcept>
#include <fmt/format.h>

#include "ramulator/base/param.h"
#include "ramulator/controller/refresh/i_refresh_manager.h"
#include "ramulator/controller/rowpolicy/i_row_policy.h"
#include "ramulator/controller/scheduler/i_scheduler.h"
#include "ramulator/controller/pud_request_validation.h"
#include "ramulator/controller/pud_sequence.h"
#include "ramulator/dram/dram_spec.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/pud_request_routing.h"

namespace Ramulator {

// ── Forwarding methods ──────────────────────────────────────────────────

void ControllerBase::set_channel_id(int channel_id) {
  IController::set_channel_id(channel_id);
  m_device.set_channel_id(channel_id);
}

bool ControllerBase::check_timing(int command, const AddrVec_t& addr_vec) {
  return m_device.check_timing(command, addr_vec, m_clk);
}

bool ControllerBase::check_request_timing(const Request& req) {
  return check_timing(req.command, req.addr_vec);
}

bool ControllerBase::validate_request_for_issue(const Request& req) {
  if (is_inherited_pud_request_type(req.type_id)) {
    if (!req.pud_locations) {
      throw std::runtime_error("PuD compute requires canonical resolved locations");
    }
    // Located compute is issued only through GenericDDR's allocated range path.
    throw std::runtime_error("PuD compute direct issue is unavailable");
  }
  if ((req.pud_locations && (!m_location_resolver || req.command < 0 || req.final_command < 0)) ||
      (m_location_resolver && is_movement_request_type(req.type_id) && !req.pud_locations)) {
    throw std::runtime_error("canonical PuD execution is unavailable");
  }
  if (!is_pud_eligible_before_prerequisite(req) ||
      m_device.conflicts_with_protected_pud(req.command, req.addr_vec)) return false;
  const bool prerequisite_compatible =
      req.command == get_preq_command(req.final_command, req.addr_vec);
  const bool timing_ready = check_request_timing(req);
  return prerequisite_compatible && timing_ready;
}

bool ControllerBase::is_pud_eligible_before_prerequisite(const Request& req) const {
  if (req.pud_locations && is_pud_request_type(req.type_id)) {
    return !m_device.conflicts_with_protected_pud(req);
  }
  // Compute uses explicit range dispatch and protected-resource intersection; it must
  // never obtain a conventional Bank-repair prerequisite here.
  if (is_inherited_pud_request_type(req.type_id)) {
    if (!req.pud_locations) {
      throw std::logic_error("PuD compute eligibility requires canonical resolved locations");
    }
    return true;
  }
  return !m_device.conflicts_with_protected_pud(req.final_command, req.addr_vec);
}

int ControllerBase::get_preq_command(int command, const AddrVec_t& addr_vec) {
  return m_device.get_preq_command(command, addr_vec, m_clk);
}

int ControllerBase::get_preq_command(const Request& req) {
  if (is_movement_request_type(req.type_id) && req.pud_locations) {
    const auto* bank = m_device.m_bank_nodes[m_device.get_flat_bank_id(req.addr_vec)];
    if (req.occurrence_index > 0 || pud_binding(*m_device.m_spec).conventional_closed(*m_device.m_spec, *bank)) {
      return req.final_command;
    }
  }
  return get_preq_command(req.final_command, req.addr_vec);
}

int ControllerBase::get_tx_bytes() const {
  return m_device.m_spec->get_tx_bytes();
}

int ControllerBase::get_num_levels() const {
  return m_device.m_spec->level_count;
}

float ControllerBase::get_tCK() const {
  return m_tCK_ps / 1000.0f;  // ps → ns
}

bool ControllerBase::supports_movement_requests() const {
  return m_device.m_spec->supports_movement_requests();
}

bool ControllerBase::supports_compute_requests() const {
  return m_device.m_spec->supports_compute_requests();
}

void ControllerBase::set_location_resolver(std::shared_ptr<const PuD::LocationResolver> resolver) {
  if (!resolver || m_location_resolver || m_clk != 0 || !m_pending.empty() ||
      m_read_buffer.size() || m_write_buffer.size() || m_pud_buffer.size() || m_priority_buffer.size()) {
    throw std::runtime_error("location resolver must be installed once before request traffic");
  }
  resolver->validate_spec(*m_device.m_spec);
  if (m_addr_mapper->m_impl->get_name() != resolver->association().routing.address_mapper) {
    throw std::runtime_error("controller mapper disagrees with location profile");
  }
  m_location_resolver = std::move(resolver);
}

// ── Shared initialization ───────────────────────────────────────────────

void ControllerBase::init_base() {
  RAMULATOR_PARSE_PARAM(m_wr_low_watermark, float, "wr_low_watermark").default_val(0.2f);
  RAMULATOR_PARSE_PARAM(m_wr_high_watermark, float, "wr_high_watermark").default_val(0.8f);
  RAMULATOR_PARSE_PARAM(m_read_buffer_size, int, "read_buffer_size").default_val(32);
  RAMULATOR_PARSE_PARAM(m_write_buffer_size, int, "write_buffer_size").default_val(32);
  // 1568 = 49 banks (4 BG × 4 banks × ~3 ranks) × 32 entries — large enough for all-bank refresh
  RAMULATOR_PARSE_PARAM(m_priority_buffer_size, int, "priority_buffer_size").default_val(1568);

  m_read_buffer.max_size = m_read_buffer_size;
  m_write_buffer.max_size = m_write_buffer_size;
  m_priority_buffer.max_size = m_priority_buffer_size;

  // Create DRAMSpec and initialize the device
  // RAMULATOR_CHILD: dram
  std::string dram_impl = m_config["dram"]["impl"].as<std::string>();
  m_device.init(DRAMSpec::create(dram_impl, m_config));

  // Cache frequently-used lookups
  m_bank_level = m_device.m_spec->get_level_id("Bank");
  m_tCK_ps = m_device.m_spec->get_timing_value("tCK_ps");

  // Active buffer holds requests with in-flight opening commands (ACT).
  // One request per bank at most, so size to total bank count.
  m_active_buffer.max_size = m_device.m_bank_nodes.size();
  m_active_per_bank.assign(m_device.m_bank_nodes.size(), 0);

  // Create sub-components (must be specified in config — no defaults)
  RAMULATOR_CREATE_CHILD(m_scheduler, IScheduler);
  RAMULATOR_CREATE_CHILD(m_refresh, IRefreshManager);
  RAMULATOR_CREATE_CHILD(m_rowpolicy, IRowPolicy);
  RAMULATOR_CREATE_CHILD(m_addr_mapper, IAddrMapper);

  // Optional plugin list — empty if not configured
  RAMULATOR_CREATE_OPTIONAL_CHILD_LIST(m_plugins, IControllerPlugin);
}

// ── Shared stats registration ───────────────────────────────────────────

void ControllerBase::setup_base(IFrontEnd* frontend, IMemorySystem* memory_system) {
  m_num_cores = frontend->get_num_cores();

  s_read_row_hits_per_core.resize(m_num_cores, 0);
  s_read_row_misses_per_core.resize(m_num_cores, 0);
  s_read_row_conflicts_per_core.resize(m_num_cores, 0);

  m_stats.add("cycles", m_measured_clk);
  m_stats.add("row_hits", s_row_hits);
  m_stats.add("row_misses", s_row_misses);
  m_stats.add("row_conflicts", s_row_conflicts);
  m_stats.add("read_row_hits", s_read_row_hits);
  m_stats.add("read_row_misses", s_read_row_misses);
  m_stats.add("read_row_conflicts", s_read_row_conflicts);
  m_stats.add("write_row_hits", s_write_row_hits);
  m_stats.add("write_row_misses", s_write_row_misses);
  m_stats.add("write_row_conflicts", s_write_row_conflicts);

  for (size_t core_id = 0; core_id < m_num_cores; core_id++) {
    m_stats.add(fmt::format("read_row_hits_core_{}", core_id), s_read_row_hits_per_core[core_id]);
    m_stats.add(fmt::format("read_row_misses_core_{}", core_id), s_read_row_misses_per_core[core_id]);
    m_stats.add(fmt::format("read_row_conflicts_core_{}", core_id), s_read_row_conflicts_per_core[core_id]);
  }

  m_stats.add("num_read_reqs", s_num_read_reqs);
  m_stats.add("num_write_reqs", s_num_write_reqs);
  m_stats.add("num_maintenance_reqs", s_num_maintenance_reqs);
  m_stats.add("num_read_reqs_served", s_num_read_reqs_served);
  m_stats.add("num_write_reqs_served", s_num_write_reqs_served);
  m_stats.add("num_maintenance_reqs_served", s_num_maintenance_reqs_served);
  m_stats.add("num_read_reqs_forwarded", s_num_read_reqs_forwarded);
  m_stats.add("num_write_reqs_coalesced", s_num_write_reqs_coalesced);
  m_stats.add("queue_len", s_queue_len);
  m_stats.add("read_queue_len", s_read_queue_len);
  m_stats.add("write_queue_len", s_write_queue_len);
  m_stats.add("priority_queue_len", s_priority_queue_len);
  m_stats.add("queue_len_avg", s_queue_len_avg);
  m_stats.add("read_queue_len_avg", s_read_queue_len_avg);
  m_stats.add("write_queue_len_avg", s_write_queue_len_avg);
  m_stats.add("priority_queue_len_avg", s_priority_queue_len_avg);
  m_stats.add("read_latency", s_read_latency);
  m_stats.add("avg_read_latency", s_avg_read_latency);

  if (m_device.m_spec->supports_compute_requests()) {
    m_stats.add("pud_queue_len", s_pud_queue_len);
    m_stats.add("pud_queue_len_avg", s_pud_queue_len_avg);
    for (int type_id = 0; type_id < Request::Type::Count; type_id++) {
      const auto slot = legacy_pud_statistic_slot(type_id);
      if (!slot.has_value()) {
        continue;
      }
      const char* stat_name = legacy_pud_statistic_name(type_id);
      m_stats.add(fmt::format("num_pud_{}_reqs", stat_name), s_num_pud_reqs[*slot]);
      m_stats.add(
          fmt::format("num_pud_{}_reqs_completed", stat_name),
          s_num_pud_reqs_completed[*slot]);
      m_stats.add(fmt::format("pud_{}_latency", stat_name), s_pud_latency[*slot]);
      m_stats.add(fmt::format("avg_pud_{}_latency", stat_name), s_avg_pud_latency[*slot]);
    }
  }

  if (m_device.m_spec->supports_movement_requests()) {
    for (int type_id : {Request::Type::LCMOV, Request::Type::GBMOV}) {
      const auto slot = movement_statistic_slot(type_id);
      const char* stat_name = movement_statistic_name(type_id);
      m_stats.add(fmt::format("num_pud_{}_reqs", stat_name), s_num_movement_reqs[*slot]);
      m_stats.add(
          fmt::format("num_pud_{}_reqs_completed", stat_name),
          s_num_movement_reqs_completed[*slot]);
      m_stats.add(fmt::format("pud_{}_latency", stat_name), s_movement_latency[*slot]);
      m_stats.add(
          fmt::format("avg_pud_{}_latency", stat_name),
          s_avg_movement_latency[*slot]);
      m_stats.add(
          fmt::format("pud_{}_moved_bits", stat_name),
          s_movement_moved_bits[*slot]);
    }
  }

  m_stats.add("read_throughput_MBps", s_read_throughput_MBps);
  m_stats.add("write_throughput_MBps", s_write_throughput_MBps);
  m_stats.add("total_throughput_MBps", s_total_throughput_MBps);
}

// ── IController overrides ───────────────────────────────────────────────

bool ControllerBase::send(Request& req) {
  if (supports_movement_requests() && is_movement_request_type(req.type_id) && !req.pud_locations) {
    throw std::runtime_error("PuD movement requires canonical resolved locations");
  }
  if (is_inherited_pud_request_type(req.type_id) && !req.pud_locations) {
    throw std::runtime_error("PuD compute requires canonical resolved locations");
  }
  if (req.pud_locations || (m_location_resolver && is_movement_request_type(req.type_id))) {
    validate_pud_routing(req, m_location_resolver ? m_location_resolver->association().routing.channels : 1);
    validate_pud_placement(req, *m_device.m_spec, m_channel_id,
                           get_pud_placement_levels(*m_device.m_spec), m_location_resolver.get());
    if (!m_location_resolver ||
        (is_inherited_pud_request_type(req.type_id) && !supports_range_aware_compute()) ||
        (is_movement_request_type(req.type_id) && !supports_movement_requests())) {
      throw std::runtime_error("canonical PuD execution is unavailable");
    }
    // Normal special-request admission retains the paired Request in the PuD
    // buffer. Only GenericDDR's allocator may acquire compute protection.
  }
  if (req.type_id < 0 || req.type_id >= static_cast<int>(m_device.m_spec->supported_requests.size())) {
    throw std::runtime_error(fmt::format(
        "DRAM standard {} does not support request type_id {}",
        m_device.m_spec->standard_name, req.type_id));
  }

  if (auto result = try_send_special_request(req); result.has_value()) {
    return *result;
  }

  if (m_device.m_spec->supported_requests[req.type_id] == DRAMSpec::CONTROLLER_SEQUENCED) {
    throw std::runtime_error(fmt::format(
        "Controller does not handle controller-sequenced request type_id {}",
        req.type_id));
  }

  // Address mapping: addr mapper populates addr_vec from intra_channel_addr.
  // PassThroughAddrMapper is a no-op (addr_vec already set by frontend).
  m_addr_mapper->apply(req);
  req.addr_vec[0] = m_channel_id;
  if (m_location_resolver) {
    // req.addr retains the original physical byte, including low offsets;
    // intra_channel_addr/addr_vec cannot replace it as a placement origin.
    resolve_ordinary_request(req, *m_location_resolver);
  }

  req.final_command = m_device.m_spec->supported_requests[req.type_id];

  // Forward existing write requests to incoming read requests
  if (req.type_id == Request::Type::Read) {
    if (m_buffered_write_addrs.count(req.addr)) {
      // The request will depart at the next cycle
      req.arrive = m_clk;
      req.depart = m_clk + 1;
      m_pending.push_back(req);
      s_num_read_reqs++;
      s_num_read_reqs_forwarded++;
      return true;
    }
  }

  // Enqueue to corresponding buffer based on request type
  bool is_success = false;
  req.arrive = m_clk;
  if (req.type_id == Request::Type::Read) {
    is_success = m_read_buffer.enqueue(req);
  } else if (req.type_id == Request::Type::Write) {
    // Coalesce: if a write to the same address is already buffered, absorb this one
    // immediately instead of occupying another buffer slot.
    if (m_buffered_write_addrs.count(req.addr)) {
      if (req.callback) {
        req.callback(req);
      }
      s_num_write_reqs++;
      s_num_write_reqs_coalesced++;
      return true;
    }
    is_success = m_write_buffer.enqueue(req);
    if (is_success) m_buffered_write_addrs.insert(req.addr);
  } else {
    throw std::runtime_error(fmt::format(
        "ControllerBase only supports Read (0) and Write (1) request types, got type_id {}", req.type_id));
  }
  if (!is_success) {
    req.arrive = -1;
    return false;
  }

  if (req.type_id == Request::Type::Read) {
    s_num_read_reqs++;
  } else if (req.type_id == Request::Type::Write) {
    s_num_write_reqs++;
  }

  return true;
}

bool ControllerBase::priority_send(Request& req) {
  if (is_inherited_pud_request_type(req.type_id) && !req.pud_locations) {
    throw std::runtime_error("PuD compute requires canonical resolved locations");
  }
  if (req.pud_locations || is_movement_request_type(req.type_id)) {
    throw std::runtime_error("canonical PuD direct priority issue is unavailable");
  }
  if (req.final_command < 0 || req.final_command >= m_device.m_spec->command_count) {
    throw std::runtime_error(fmt::format(
        "Invalid priority request final_command {}: expected a DRAM command id in [0, {})",
        req.final_command,
        m_device.m_spec->command_count));
  }

  bool is_success = m_priority_buffer.enqueue(req);
  if (is_success && req.type_id == -1) {
    s_num_maintenance_reqs++;
  }
  return is_success;
}

// ── Tick preamble ───────────────────────────────────────────────────────

void ControllerBase::tick_prologue() {
  m_clk++;
  m_measured_clk++;

  s_queue_len +=
      m_read_buffer.size() + m_write_buffer.size() + m_priority_buffer.size() + m_pud_buffer.size();
  s_read_queue_len += m_read_buffer.size();
  s_write_queue_len += m_write_buffer.size();
  s_priority_queue_len += m_priority_buffer.size();
  s_pud_queue_len += m_pud_buffer.size();

  serve_completed_requests();
}

// ── Request lifecycle ────────────────────────────────────────────────────

bool ControllerBase::pud_compute_resources_available(const Request& req) const {
  if (!req.pud_locations || !is_inherited_pud_request_type(req.type_id)) {
    throw std::logic_error("Compute reservation requires a located compute request");
  }
  validate_pud_placement(req, *m_device.m_spec, m_channel_id,
                         get_pud_placement_levels(*m_device.m_spec), m_location_resolver.get());
  for (const auto& record : m_protected_pud) {
    if (req.pud_locations->conflicts(*record.context->locations())) return false;
  }
  // This is occupied-resource availability, not full start eligibility or
  // command readiness. Geometry is supplied solely by the retained resolver.
  return true;
}

bool ControllerBase::pud_compute_start_eligible(const Request& req) const {
  if (!m_priority_buffer.buffer.empty() || !is_pud_eligible_before_prerequisite(req)) return false;
  const int bank_id = m_device.get_flat_bank_id(req.operands.front());
  const auto* bank = m_device.m_bank_nodes[bank_id];
  // Ordinary active work drains before compute reservation. Range-aware
  // ranges are separate and do not make conventional Bank state Opened.
  for (const auto& active : m_active_buffer.buffer) {
    if (active.pud_locations && is_movement_request_type(active.type_id)) continue;
    if (is_inherited_pud_request_type(active.type_id)) {
      if (!active.pud_locations) {
        throw std::logic_error("Active PuD compute is missing canonical resolved locations");
      }
      continue;
    }
    if (m_device.get_flat_bank_id(active.addr_vec) == bank_id) return false;
  }
  if (!pud_binding(*m_device.m_spec).conventional_drained(*m_device.m_spec, *bank)) return false;
  // Incoming conventional PRE/AP/REF recovery is distinct from local primitive
  // readiness. No range-aware compute command updates these hierarchical deadlines.
  const auto first = describe_pud_occurrence(req, 0, *m_device.m_spec);
  return m_device.m_root->check_timing(first.command, req.operands.front(), m_clk);
}

bool ControllerBase::reserve_pud_compute(Request& req) {
  const std::weak_ptr<PuDExecutionContext> empty;
  if (req.pud_context.owner_before(empty) || empty.owner_before(req.pud_context)) {
    throw std::logic_error("Request already has a current or stale compute reservation");
  }
  if (!pud_compute_resources_available(req) || !pud_compute_start_eligible(req)) return false;
  std::shared_ptr<PuDExecutionContext> context = m_device.make_pud_context(req);
  m_device.protect_pud(context);
  // Commit the complete footprint; a failed reservation changes no Request.
  // A failed insertion leaves only an expired non-owning Device reference.
  m_protected_pud.push_back({std::move(context), false});
  req.pud_context = m_protected_pud.back().context;
  return true;
}

PuDExecutionContext& ControllerBase::protected_pud_context(const Request& req) const {
  const auto context = req.pud_context.lock();
  const auto it = std::find_if(m_protected_pud.begin(), m_protected_pud.end(),
      [&](const auto& record) { return record.context == context; });
  if (!context || it == m_protected_pud.end() || context->locations() != req.pud_locations) {
    throw std::logic_error("Missing, foreign or stale protected PuD invocation context");
  }
  return *context;
}

bool ControllerBase::check_pud_compute_issue(const Request& req) {
  const auto& context = protected_pud_context(req);
  if (!is_pud_eligible_before_prerequisite(req)) return false;
  const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, *m_device.m_spec);
  return m_device.check_pud_timing(req, occurrence, &context, m_clk);
}

void ControllerBase::issue_pud_compute(Request& req) {
  if (!check_pud_compute_issue(req)) throw std::logic_error("Compute issue timing or eligibility not ready");
  const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, *m_device.m_spec);
  m_device.issue_pud_command(req, occurrence, &protected_pud_context(req), m_clk);
}

bool ControllerBase::check_pud_movement_issue(const Request& req) {
  if (!is_pud_eligible_before_prerequisite(req)) return false;
  // First ACT acquisition waits for ordinary active work, even if its Bank
  // happens to be Closed. No protection is acquired by this probe.
  if (req.occurrence_index == 0) {
    const int bank = m_device.get_flat_bank_id(req.addr_vec);
    for (const auto& active : m_active_buffer.buffer) {
      if (!is_pud_request_type(active.type_id) &&
          m_device.get_flat_bank_id(active.addr_vec) == bank) return false;
    }
  }
  const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, *m_device.m_spec);
  if (req.pud_context.expired()) {
    const auto context = m_device.make_pud_context(req);
    return m_device.check_pud_timing(req, occurrence, context.get(), m_clk);
  }
  return m_device.check_pud_timing(req, occurrence, &protected_pud_context(req), m_clk);
}

void ControllerBase::issue_pud_movement(Request& req) {
  if (!check_pud_movement_issue(req)) throw std::logic_error("Movement issue is not ready");
  if (req.pud_context.expired()) {
    std::shared_ptr<PuDExecutionContext> context = m_device.make_pud_context(req);
    m_device.protect_pud(context);
    m_protected_pud.push_back({std::move(context), false});
    req.pud_context = m_protected_pud.back().context;
  }
  const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, *m_device.m_spec);
  m_device.issue_pud_command(req, occurrence, &protected_pud_context(req), m_clk);
}

ControllerBase::ProtectedPuD& ControllerBase::protected_pud_record(const Request& req) {
  const auto* context = &protected_pud_context(req);
  return *std::find_if(m_protected_pud.begin(), m_protected_pud.end(),
      [&](const auto& record) { return record.context.get() == context; });
}

void ControllerBase::release_completed_resources(Request& req) {
  if (!is_pud_request_type(req.type_id)) return;
  if (!req.pud_locations) {
    throw std::logic_error("PuD completion requires canonical resolved locations");
  }
  const auto& record = protected_pud_record(req);
  if (!record.completion_pending || record.context->phase() != PuDExecutionContext::Phase::Recovering ||
      req.depart < 0 || req.depart > m_clk) {
    throw std::logic_error("PuD completion precedes protected recovery");
  }
  const auto* context = record.context.get();
  std::erase_if(m_protected_pud,
      [&](const auto& held) { return held.context.get() == context; });
  // Release conflict-registry references at recovery too, including the final
  // invocation when no later allocation will prune expired entries.
  std::erase_if(m_device.m_protected_pud, [](const auto& held) { return held.expired(); });
  req.pud_context.reset();
}

void ControllerBase::retire_request(ReqBuffer::iterator& req_it, ReqBuffer& buffer) {
  ProtectedPuD* protected_invocation = nullptr;
  if (is_pud_request_type(req_it->type_id)) {
    if (!req_it->pud_locations) {
      throw std::logic_error("PuD retirement requires canonical resolved locations");
    }
    protected_invocation = &protected_pud_record(*req_it);
    const auto& context = *protected_invocation->context;
    if (protected_invocation->completion_pending || context.phase() != PuDExecutionContext::Phase::Recovering ||
        req_it->occurrence_index != get_pud_sequence_length(*req_it) ||
        req_it->occurrence_issue_history.size() != get_pud_sequence_length(*req_it) ||
        req_it->occurrence_issue_history.back() == Request::kOccurrenceNotIssued ||
        req_it->occurrence_issue_history.back() > m_clk) {
      throw std::logic_error("PuD retirement requires its unretired terminal PRE");
    }
  }
  if (&buffer == &m_active_buffer) {
    m_active_per_bank[m_device.get_flat_bank_id(req_it->addr_vec)]--;
  }
  if (&buffer == &m_write_buffer) {
    m_buffered_write_addrs.erase(req_it->addr);
  }

  if (req_it->type_id == Request::Type::Read) {
    // Read: completion with read latency
    req_it->depart = m_clk + m_device.m_spec->read_latency;
    m_pending.push_back(*req_it);
    s_num_read_reqs_served++;
  } else if (req_it->type_id == Request::Type::Write) {
    // Write: For now we call the callback here.
    // TODO: We could also do it after a write_latency (e.g., nCWL+nBL)
    // similarily as reads
    if (req_it->callback) {
      req_it->callback(*req_it);
    }
    s_num_write_reqs_served++;
  } else if (is_pud_request_type(req_it->type_id)) {
    // Request history is the sole terminal-issue authority; retirement time
    // need not be substituted for it. Delayed completion owns recovery release.
    req_it->depart = pud_binding(*m_device.m_spec).recovery_deadline(
        *m_device.m_spec, *req_it, m_clk, protected_invocation != nullptr);
    m_pending.push_back(*req_it);
    if (protected_invocation) protected_invocation->completion_pending = true;
  } else if (req_it->type_id == -1) {
    s_num_maintenance_reqs_served++;
  }
  // Maintenance/direct-command requests are removed once their terminal command issues.
  buffer.remove(req_it);
}

void ControllerBase::promote_to_active(ReqBuffer::iterator& req_it, ReqBuffer& buffer) {
  // Transfer the sole schedulable progression: successful enqueue erases the
  // source before scheduling resumes; backpressure leaves only the source.
  if (m_active_buffer.enqueue(*req_it)) {
    m_active_per_bank[m_device.get_flat_bank_id(req_it->addr_vec)]++;
    if (&buffer == &m_write_buffer) {
      m_buffered_write_addrs.erase(req_it->addr);
    }
    buffer.remove(req_it);
  }
}

// ── Systematic scheduling ────────────────────────────────────────────────

ControllerBase::Candidate ControllerBase::pick_best_ready_from(
    ReqBuffer& buffer,
    RequestFilterRef command_filter,
    RequestFilterRef eligibility_filter) {
  Candidate c;
  auto it = m_scheduler->get_best_request(buffer, eligibility_filter, command_filter);
  if (it == buffer.end()) {
    return c;
  }
  if (!check_request_timing(*it)) {
    return c;
  }
  c.valid = true;
  c.it = it;
  c.buffer = &buffer;
  return c;
}

ControllerBase::Candidate ControllerBase::pick_priority_if(
    RequestFilterRef command_filter,
    RequestFilterRef eligibility_filter) {
  Candidate c;
  if (m_priority_buffer.size() == 0) {
    return c;
  }

  auto it = m_priority_buffer.begin();
  if (eligibility_filter && !eligibility_filter(*it)) {
    return c;
  }
  it->command = get_preq_command(it->final_command, it->addr_vec);
  if (!check_request_timing(*it)) {
    return c;
  }
  if (would_close_active(*it)) {
    return c;
  }
  if (command_filter && !command_filter(*it)) {
    return c;
  }

  c.valid = true;
  c.it = it;
  c.buffer = &m_priority_buffer;
  return c;
}

ControllerBase::Candidate ControllerBase::pick_rw_if(
    RequestFilterRef command_filter,
    RequestFilterRef eligibility_filter) {
  set_write_mode();
  auto& buffer = m_is_write_mode ? m_write_buffer : m_read_buffer;
  return pick_best_ready_from(buffer, [&](const Request& req) {
    if (would_close_active(req)) {
      return false;
    }
    return !command_filter || command_filter(req);
  }, eligibility_filter);
}

bool ControllerBase::would_close_active(const Request& req) const {
  if (!m_device.m_spec->command_meta[req.command].is_closing) {
    return false;
  }
  if (is_inherited_pud_request_type(req.type_id)) {
    if (!req.pud_locations) {
      throw std::logic_error("PuD compute close check requires canonical resolved locations");
    }
  }
  if (is_inherited_pud_request_type(req.type_id) && !req.pud_context.expired() &&
      req.command == req.final_command) {
    protected_pud_context(req);
    const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, *m_device.m_spec);
    if (occurrence.terminal && req.command == occurrence.command) {
      return false;  // Its terminal PRE closes only its associated range.
    }
  }
  if (m_device.conflicts_with_protected_pud(req.command, req.addr_vec)) return true;
  if (m_active_buffer.size() == 0) {
    return false;
  }

  auto target = m_device.m_spec->bank_targets[req.command];

  // Hot path: single-bank close (PREpb, RDA, WRA) — O(1) lookup.
  if (target == BankTarget::Single) {
    return m_active_per_bank[m_device.get_flat_bank_id(req.addr_vec)] > 0;
  }

  // All / SameBank: scan occupied banks with proper scope checking.
  // These are rare maintenance commands — linear scan skipping zeros is fine.
  for (int i = 0; i < static_cast<int>(m_active_per_bank.size()); i++) {
    if (m_active_per_bank[i] == 0) {
      continue;
    }
    if (target == BankTarget::SameBank &&
        m_device.m_bank_nodes[i]->m_node_id != req.addr_vec[m_bank_level]) {
      continue;
    }
    if (m_device.bank_matches(m_device.m_bank_nodes[i], req.addr_vec)) {
      return true;
    }
  }
  return false;
}

void ControllerBase::update_request_stats(ReqBuffer::iterator& req) {
  req->is_stat_updated = true;

  if (req->type_id == Request::Type::Read) {
    if (m_device.check_rowbuffer_hit(req->final_command, req->addr_vec, m_clk)) {
      s_read_row_hits++;
      s_row_hits++;
      if (req->source_id != -1) {
        s_read_row_hits_per_core[req->source_id]++;
      }
    } else if (m_device.check_node_open(req->final_command, req->addr_vec, m_clk)) {
      s_read_row_conflicts++;
      s_row_conflicts++;
      if (req->source_id != -1) {
        s_read_row_conflicts_per_core[req->source_id]++;
      }
    } else {
      s_read_row_misses++;
      s_row_misses++;
      if (req->source_id != -1) {
        s_read_row_misses_per_core[req->source_id]++;
      }
    }
  } else if (req->type_id == Request::Type::Write) {
    if (m_device.check_rowbuffer_hit(req->final_command, req->addr_vec, m_clk)) {
      s_write_row_hits++;
      s_row_hits++;
    } else if (m_device.check_node_open(req->final_command, req->addr_vec, m_clk)) {
      s_write_row_conflicts++;
      s_row_conflicts++;
    } else {
      s_write_row_misses++;
      s_row_misses++;
    }
  }
}

void ControllerBase::serve_completed_requests() {
  // Read and PuD recovery latencies can differ, so pending requests are not
  // necessarily ordered by depart. Re-scan after each callback because the
  // callback may append to m_pending and invalidate all deque iterators.
  while (true) {
    auto it = std::find_if(
        m_pending.begin(), m_pending.end(),
        [&](const Request& req) { return req.depart <= m_clk; });
    if (it == m_pending.end()) {
      break;
    }

    Request completed = std::move(*it);
    m_pending.erase(it);

    // Recovery protection outlives command retirement. Erase its footprint
    // record before accounting/callback, so reentrant successors can reuse it.
    release_completed_resources(completed);

    const size_t latency = static_cast<size_t>(completed.depart - completed.arrive);
    if (completed.type_id == Request::Type::Read) {
      s_read_latency += latency;
    } else if (const auto slot = legacy_pud_statistic_slot(completed.type_id);
               slot.has_value()) {
      s_num_pud_reqs_completed[*slot]++;
      s_pud_latency[*slot] += latency;
    } else if (const auto slot = movement_statistic_slot(completed.type_id);
               slot.has_value()) {
      s_num_movement_reqs_completed[*slot]++;
      s_movement_latency[*slot] += latency;
      s_movement_moved_bits[*slot] +=
          get_movement_moved_bits(completed, *m_device.m_spec);
    }
    if (completed.callback) {
      completed.callback(completed);
    }
  }
}

void ControllerBase::set_write_mode() {
  if (!m_is_write_mode) {
    if ((m_write_buffer.size() > m_wr_high_watermark * m_write_buffer.max_size) || m_read_buffer.size() == 0) {
      m_is_write_mode = true;
    }
  } else {
    if ((m_write_buffer.size() < m_wr_low_watermark * m_write_buffer.max_size) && m_read_buffer.size() != 0) {
      m_is_write_mode = false;
    }
  }
}

void ControllerBase::update_stats() {
  s_avg_read_latency = (s_num_read_reqs_served > 0) ? (float)s_read_latency / (float)s_num_read_reqs_served : 0;
  for (size_t i = 0; i < kNumLegacyPuDStatisticSlots; i++) {
    s_avg_pud_latency[i] = s_num_pud_reqs_completed[i] > 0
        ? static_cast<float>(s_pud_latency[i]) / static_cast<float>(s_num_pud_reqs_completed[i])
        : 0;
  }
  for (size_t i = 0; i < kNumMovementStatisticSlots; i++) {
    s_avg_movement_latency[i] = s_num_movement_reqs_completed[i] > 0
        ? static_cast<float>(s_movement_latency[i]) /
              static_cast<float>(s_num_movement_reqs_completed[i])
        : 0;
  }

  s_queue_len_avg = (m_measured_clk > 0) ? (float)s_queue_len / (float)m_measured_clk : 0;
  s_read_queue_len_avg = (m_measured_clk > 0) ? (float)s_read_queue_len / (float)m_measured_clk : 0;
  s_write_queue_len_avg = (m_measured_clk > 0) ? (float)s_write_queue_len / (float)m_measured_clk : 0;
  s_priority_queue_len_avg = (m_measured_clk > 0) ? (float)s_priority_queue_len / (float)m_measured_clk : 0;
  s_pud_queue_len_avg = (m_measured_clk > 0) ? (float)s_pud_queue_len / (float)m_measured_clk : 0;

  int tx_bytes = m_device.m_spec->get_tx_bytes();
  float time_ps = static_cast<float>(m_measured_clk) * m_tCK_ps;
  s_read_throughput_MBps = (time_ps > 0) ? s_num_read_reqs_served * tx_bytes * 1e6f / time_ps : 0;
  s_write_throughput_MBps = (time_ps > 0) ? s_num_write_reqs_served * tx_bytes * 1e6f / time_ps : 0;
  s_total_throughput_MBps = s_read_throughput_MBps + s_write_throughput_MBps;
}

void ControllerBase::finalize() {
  update_stats();
}

void ControllerBase::reset_stats() {
  m_measured_clk = 0;

  s_row_hits = 0;
  s_row_misses = 0;
  s_row_conflicts = 0;
  s_read_row_hits = 0;
  s_read_row_misses = 0;
  s_read_row_conflicts = 0;
  s_write_row_hits = 0;
  s_write_row_misses = 0;
  s_write_row_conflicts = 0;

  std::fill(s_read_row_hits_per_core.begin(), s_read_row_hits_per_core.end(), 0);
  std::fill(s_read_row_misses_per_core.begin(), s_read_row_misses_per_core.end(), 0);
  std::fill(s_read_row_conflicts_per_core.begin(), s_read_row_conflicts_per_core.end(), 0);

  s_num_read_reqs = 0;
  s_num_write_reqs = 0;
  s_num_maintenance_reqs = 0;
  s_num_read_reqs_served = 0;
  s_num_write_reqs_served = 0;
  s_num_maintenance_reqs_served = 0;
  s_num_read_reqs_forwarded = 0;
  s_num_write_reqs_coalesced = 0;

  s_queue_len = 0;
  s_read_queue_len = 0;
  s_write_queue_len = 0;
  s_priority_queue_len = 0;
  s_pud_queue_len = 0;
  s_queue_len_avg = 0;
  s_read_queue_len_avg = 0;
  s_write_queue_len_avg = 0;
  s_priority_queue_len_avg = 0;
  s_pud_queue_len_avg = 0;

  s_read_latency = 0;
  s_avg_read_latency = 0;
  s_num_pud_reqs.fill(0);
  s_num_pud_reqs_completed.fill(0);
  s_pud_latency.fill(0);
  s_avg_pud_latency.fill(0);
  s_num_movement_reqs.fill(0);
  s_num_movement_reqs_completed.fill(0);
  s_movement_latency.fill(0);
  s_avg_movement_latency.fill(0);
  s_movement_moved_bits.fill(0);
  s_read_throughput_MBps = 0;
  s_write_throughput_MBps = 0;
  s_total_throughput_MBps = 0;
}

}  // namespace Ramulator
