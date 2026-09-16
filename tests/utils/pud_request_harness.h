#ifndef RAMULATOR_TESTS_PUD_REQUEST_HARNESS_H
#define RAMULATOR_TESTS_PUD_REQUEST_HARNESS_H

#include "ramulator/controller/rowpolicy/i_row_policy.h"

// Preserve the DDR4 fixture's public two-deadline view of combined-bus ID 0.
inline Clk_t ddr4_test_deadline(const std::map<int, Clk_t>& deadlines) {
  const auto it = deadlines.find(0);
  return it == deadlines.end() ? -1 : it->second;
}

// W2 component fixtures exercise retention without enabling execution.
inline std::vector<std::vector<int>> region_cells(const PuD::LocationResolver& resolver,
                                                  const PuD::ResolvedRegion& region) {
  std::vector<std::vector<int>> cells;
  for (int64_t i = 0; i < region.cell_count; ++i) {
    cells.push_back(LocationResolverUnderTest::cell_vector(resolver.cell_at(region, i)));
  }
  return cells;
}

inline nb::dict located_snapshot(const Request& req, bool cells) {
  nb::dict out;
  out["external"] = req.operands;
  out["addr_vec"] = req.addr_vec;
  out["cursor"] = req.occurrence_index;
  out["history"] = req.occurrence_issue_history;
  out["size_bytes"] = req.size_bytes;
  out["retained"] = static_cast<bool>(req.pud_locations);
  nb::list operands;
  if (req.pud_locations) {
    for (const auto& pair : req.pud_locations->operands) {
      const auto& region = pair.location;
      const auto& o = region.origin;
      nb::dict item;
      auto coordinates = o.bank;
      coordinates.insert(coordinates.end(), {o.subarray, o.local_row});
      item["origin"] = coordinates;
      item["range"] = std::vector<int>{o.mats.first, o.mats.last};
      item["group"] = o.group ? nb::cast(o.group->value) : nb::none();
      item["burst"] = region.burst ? nb::cast(region.burst->value) : nb::none();
      item["cell_count"] = region.cell_count;
      item["profile"] = region.association->profile.name;
      item["address_space"] = region.association->routing.address_space;
      if (cells) {
        item["cells"] = region_cells(*req.pud_locations->resolver, region);
      }
      operands.append(item);
    }
  }
  out["locations"] = operands;
  return out;
}

inline Request located_request(const LocationResolverUnderTest& fixture, int type, nb::list descriptors, int size) {
  std::vector<PuD::PairedOperand> operands;
  for (auto value : descriptors) {
    auto d = nb::cast<nb::dict>(value);
    // This fixture exposes the production single LayoutRegion contract. It
    // cannot represent sparse/per-mat selectors or silently widen scalar bits.
    for (auto [key, unused] : d) {
      auto name = nb::cast<std::string>(key);
      if (name != "kind" && name != "row" && name != "range" && name != "target" &&
          name != "group" && name != "column") {
        throw std::invalid_argument("unsupported region descriptor");
      }
    }
    auto row = nb::cast<std::vector<int>>(d["row"]);
    auto kind = nb::cast<std::string>(d["kind"]);
    if (kind != "compute" && kind != "group" && kind != "layout") {
      throw std::invalid_argument("PuD operand requires an explicit layout region, not a bit anchor");
    }
    const bool has_range = d.contains("range");
    const bool has_target = d.contains("target");
    if (has_target && nb::cast<std::string>(d["target"]) != "FULL_MAT") {
      throw std::invalid_argument("compute target must be FULL_MAT");
    }
    const bool full_mat = has_target;
    if (has_range == full_mat) {
      throw std::invalid_argument("exactly one of MatRange or FULL_MAT is required");
    }
    if (full_mat && kind != "compute") {
      throw std::invalid_argument("FULL_MAT is only a compute construction target");
    }
    std::vector<int> mats;
    if (has_range) {
      mats = nb::cast<std::vector<int>>(d["range"]);
      if (mats.size() != 2) {
        throw std::invalid_argument("one inclusive contiguous range required");
      }
    }
    std::optional<int> group;
    if (d.contains("group")) {
      group = nb::cast<int>(d["group"]);
    }
    std::optional<PuD::BurstColumn> column;
    if (d.contains("column")) {
      column = PuD::BurstColumn{nb::cast<int>(d["column"])};
    }
    auto region = full_mat
        ? fixture.resolver()->compute_footprint(LocationResolverUnderTest::row(row), PuD::FULL_MAT)
        : fixture.region(kind, row, mats[0], mats[1], group);
    operands.push_back(fixture.resolver()->pair(std::move(region), column));
  }
  Request req(fixture.resolver(), std::move(operands), type);
  req.source_id = 0;
  req.size_bytes = size;
  return req;
}

// Capture the actual GenericDDR instance while constructing a real GenericDRAM
// system; no production controller discovery API is needed for these tests.
class LocationHarnessObserver final : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, LocationHarnessObserver, "LocationHarnessObserver");

 public:
  inline static ControllerBase* created_controller = nullptr;
  nb::list events;
  void init() override {
    created_controller = cast_parent<ControllerBase>();
  }
  void on_issue(const Request& req) override {
    auto out = located_snapshot(req, false);
    auto* controller = cast_parent<ControllerBase>();
    out["clk"] = controller->m_clk;
    out["command"] = controller->m_device.m_spec->command_names.at(req.command);
    out["source_id"] = req.source_id;
    out["allocated"] = !req.pud_context.expired();
    events.append(out);
  }
};

class LocatedSystemUnderTest {
 public:
  LocatedSystemUnderTest(nb::dict controller, const LocationResolverUnderTest& fixture,
                         const std::string& channel_mapper, bool install)
      : m_frontend(std::make_unique<HarnessFrontEnd>(64)), m_resolver(fixture.resolver()) {
    auto config = py_to_confignode(controller);
    auto plugins = config["controller_plugins"];
    if (!plugins.is_sequence()) plugins = ConfigNode(ConfigNode::Seq{});
    plugins.push_back(ConfigNode::Map{{"impl", "LocationHarnessObserver"}});
    config.set("controller_plugins", std::move(plugins));
    LocationHarnessObserver::created_controller = nullptr;
    ConfigNode sys(ConfigNode::Map{{"impl", "GenericDRAM"},
                                   {"clock_ratio", 1},
                                   {"channel_mapper", ConfigNode::Map{{"impl", channel_mapper}}},
                                   {"controllers", ConfigNode::Seq{config}}});
    m_system = Factory::create_memory_system(wrap_interface_config(IMemorySystem::get_name(), sys));
    m_owner.reset(dynamic_cast<Implementation*>(m_system));
    m_controller = LocationHarnessObserver::created_controller;
    if (!m_controller) {
      throw std::runtime_error("missing observed controller");
    }
    m_frontend->connect_memory_system(m_system);
    m_system->connect_frontend(m_frontend.get());
    if (m_system->location_resolver()) {
      m_resolver = m_system->location_resolver();
    } else if (install) {
      m_controller->set_location_resolver(m_resolver);
    }
  }
  bool send(Request& req, const std::string& path) {
    if (path == "controller") {
      return m_controller->send(req);
    }
    if (path == "priority") {
      return m_controller->priority_send(req);
    }
    if (path == "issue") {
      return m_controller->validate_request_for_issue(req);
    }
    return m_system->send(req);
  }
  Request request(int type, nb::list descriptors, int size) const {
    return located_request(LocationResolverUnderTest(m_resolver), type, descriptors, size);
  }
  bool submit(Request req, int source, nb::object callback) {
    if (source < 0 || source >= m_frontend->get_num_cores()) throw std::invalid_argument("invalid fixture source_id");
    req.source_id = source;
    req.callback = [this, callback](Request& done) {
      auto out = located_snapshot(done, false);
      out["source_id"] = done.source_id;
      out["arrive"] = done.arrive;
      out["depart"] = done.depart;
      out["held"] = m_controller->m_protected_pud.size();
      completed.append(out);
      if (!callback.is_none()) callback(out);
    };
    return m_system->send(req);
  }
  bool submit_ordinary(Addr_t addr, int type, int source) {
    Request req(addr, type);
    req.size_bytes = m_system->get_tx_bytes();
    return submit(std::move(req), source, nb::none());
  }
  void advance(Clk_t clk) {
    while (m_controller->m_clk < clk) m_system->tick();
  }
  nb::list issued() const {
    for (auto* plugin : m_controller->m_plugins) {
      if (auto* observer = dynamic_cast<LocationHarnessObserver*>(plugin)) return observer->events;
    }
    throw std::logic_error("missing observer");
  }
  nb::list completions() const { return completed; }
  nb::dict scheduling() const {
    nb::dict out;
    nb::list pending, recovering;
    auto snapshot = [&](const Request& req) {
      auto item = located_snapshot(req, false);
      item["source_id"] = req.source_id;
      item["arrive"] = req.arrive;
      const auto context = req.pud_context.lock();
      item["phase"] = context ? static_cast<int>(context->phase()) : -1;
      return item;
    };
    for (const auto& req : m_controller->m_pud_buffer.buffer) pending.append(snapshot(req));
    for (const auto& req : m_controller->m_pending) recovering.append(snapshot(req));
    out["pending"] = pending;
    out["recovering"] = recovering;
    out["held"] = m_controller->m_protected_pud.size();
    out["active_size"] = m_controller->m_active_buffer.size();
    return out;
  }
  nb::dict ordinary(Addr_t address, int type, int size, bool cells, std::optional<Addr_t> wrong_intra) {
    Request req(address, type);
    req.source_id = 0;
    req.size_bytes = size;
    bool callback_had_locations = false;
    req.callback = [&](Request& completed) { callback_had_locations |= bool(completed.pud_locations); };
    bool accepted;
    if (wrong_intra) {
      req.intra_channel_addr = *wrong_intra;
      accepted = m_controller->send(req);
    } else {
      accepted = m_system->send(req);
    }
    const auto locations = resolve_ordinary_request(req, *m_resolver);
    nb::dict out;
    out["accepted"] = accepted;
    out["external"] = req.addr_vec;
    out["origin"] = std::vector<int64_t>{locations.origin.origin.byte, locations.origin.origin.bit};
    out["cell"] = LocationResolverUnderTest::cell_vector(locations.origin.cell);
    out["group"] = locations.origin.group.value;
    out["requested_size_bytes"] = locations.requested_size_bytes;
    out["activation_count"] = locations.activation.cell_count;
    out["burst_count"] = locations.burst.cell_count;
    out["retained"] = bool(req.pud_locations);
    if (cells) {
      out["activation"] = region_cells(*m_resolver, locations.activation);
      out["burst"] = region_cells(*m_resolver, locations.burst);
    }
    for (int i = 0; i < 200; ++i) {
      m_system->tick();
    }
    out["completion_retained"] = callback_had_locations;
    return out;
  }
  nb::dict stats() const {
    m_system->update_stats_recursive();
    return nb::cast<nb::dict>(confignode_to_py(m_system->collect_stats()));
  }
  nb::dict forwarding() {
    int callbacks = 0;
    bool retained = false;
    for (int type : {Request::Type::Write, Request::Type::Write, Request::Type::Read}) {
      Request req(7, type);
      req.source_id = 0;
      req.size_bytes = 1;
      req.callback = [&](Request& completed) {
        ++callbacks;
        retained |= bool(completed.pud_locations);
      };
      if (!m_system->send(req)) {
        throw std::runtime_error("ordinary fixture enqueue failed");
      }
    }
    for (int i = 0; i < 200; ++i) {
      m_system->tick();
    }
    nb::dict out;
    out["callbacks"] = callbacks;
    out["retained"] = retained;
    out["stats"] = stats();
    return out;
  }
  size_t pending() const {
    return m_controller->pending_pud_requests().size();
  }

 private:
  std::unique_ptr<HarnessFrontEnd> m_frontend;
  std::unique_ptr<Implementation> m_owner;
  IMemorySystem* m_system = nullptr;
  ControllerBase* m_controller = nullptr;
  std::shared_ptr<const PuD::LocationResolver> m_resolver;
  nb::list completed;
};

// W3 component-only execution: fixtures provide separate ranges directly. No
// production scheduler, physical protection or completion is installed.
class ComputeRangesUnderTest {
 public:
  explicit ComputeRangesUnderTest(nb::dict dram) {
    auto cfg = py_to_confignode(dram);
    device.init(DRAMSpec::create(cfg["impl"].as<std::string>(), ConfigNode(ConfigNode::Map{{"dram", cfg}})));
  }
  size_t add(Request req) {
    initialize_pud_sequence(req, *device.m_spec);
    std::shared_ptr<PuDExecutionContext> context = device.make_pud_context(req);
    device.protect_pud(context);
    req.pud_context = context;
    records.push_back({std::move(req), std::move(context)});
    return records.size() - 1;
  }
  size_t save(size_t id) {
    const auto& req = records.at(id).req;
    saved.push_back(describe_pud_occurrence(req, req.occurrence_index, *device.m_spec));
    return saved.size() - 1;
  }
  void corrupt_occurrence(size_t id, const std::string& field) {
    auto& occurrence = saved.at(id);
    if (field == "wrong_operand") occurrence.operand_index ^= 1;
    else if (field == "wrong_role") occurrence.role = occurrence.role == PuDOccurrenceRole::Source
        ? PuDOccurrenceRole::Destination : PuDOccurrenceRole::Source;
    else if (field == "wrong_index") ++occurrence.index;
    else if (field == "terminal") occurrence.terminal = !occurrence.terminal;
    else if (field == "unassociated") occurrence.locations.reset();
    else throw std::invalid_argument("unknown occurrence corruption");
  }
  bool dispatch(size_t id, Clk_t clk, bool issue, int context_id, int saved_occurrence,
                const std::string& command, bool foreign_device) {
    auto& record = records.at(id);
    auto& req = record.req;
    auto occurrence = saved_occurrence < 0 ? describe_pud_occurrence(req, req.occurrence_index, *device.m_spec)
                                     : saved.at(saved_occurrence);
    if (!command.empty()) occurrence.command = device.m_spec->get_command_id(command);
    auto* context = context_id == -2 ? nullptr : records.at(context_id < 0 ? id : context_id).context.get();
    // A second Device rejects a context minted by the first before any access.
    DRAMDevice other;
    auto& target = foreign_device ? other : device;
    const bool ready = target.check_pud_timing(req, occurrence, context, clk);
    if (!issue) return ready;
    if (!ready) throw std::logic_error("PuD invocation timing not ready");
    target.issue_pud_command(req, occurrence, context, clk);
    // Exercise Request relocation after every action, retaining one cursor.
    Request copied = req;
    req = std::move(copied);
    return true;
  }
  nb::dict state(size_t id) const {
    const auto& record = records.at(id);
    const auto& context = *record.context;
    nb::dict out = located_snapshot(record.req, false);
    static const char* phases[] = {"Closed", "PuDChargeSharing", "PuDSensed", "Recovering"};
    out["phase"] = phases[static_cast<int>(context.phase())];
    // Observation only: active identities come from the authoritative issued
    // prefix. Terminal PRE closes that view without erasing Request history.
    std::vector<size_t> activated;
    std::vector<AddrVec_t> rows;
    if (context.phase() != PuDExecutionContext::Phase::Recovering) {
      for (size_t i = 0; i < record.req.occurrence_index; ++i) {
        if (record.req.occurrence_issue_history.at(i) == Request::kOccurrenceNotIssued) continue;
        const auto occurrence = describe_pud_occurrence(record.req, i, *device.m_spec);
        if (!device.m_spec->command_meta[occurrence.command].is_opening) continue;
        activated.push_back(occurrence.operand_index);
        rows.push_back(occurrence.location()->external);
      }
    }
    out["activated_operands"] = activated;
    out["activated_rows"] = rows;
    out["same_bundle"] = record.req.pud_locations == context.locations();
    return out;
  }
  nb::list shared() const {
    nb::list out;
    for (int level = 0; level <= device.m_bank_level; ++level) {
      device.m_root->for_each_at_level(level, [&](DRAMNode* node) {
        nb::dict item;
        item["level"] = level;
        if (level == 0) item["command_occupancy"] =
            std::vector<Clk_t>{ddr4_test_deadline(device.m_pud_resource_ready),
                              ddr4_test_deadline(device.m_command_resource_ready)};
        item["id"] = node->m_node_id;
        item["state"] = node->m_state;
        item["rows"] = std::map<int, int>(node->m_row_state.begin(), node->m_row_state.end());
        item["ready"] = node->m_cmd_ready_clk;
        std::vector<std::vector<Clk_t>> history;
        for (const auto& h : node->m_cmd_history) history.emplace_back(h.begin(), h.end());
        item["history"] = history;
        out.append(item);
      });
    }
    return out;
  }
  bool raw(const std::string& command, const AddrVec_t& addr, Clk_t clk, bool issue) {
    int cmd = device.m_spec->get_command_id(command);
    bool ready = device.get_preq_command(cmd, addr, clk) == cmd && device.check_timing(cmd, addr, clk);
    if (issue) {
      if (!ready) throw std::logic_error("raw fixture command not ready");
      device.issue_command(cmd, addr, clk);
    }
    return ready;
  }
  void skip(size_t id) {
    auto& req = records.at(id).req;
    observe_pud_command_issue(req, req.final_command, 123, *device.m_spec);
  }

 private:
  DRAMDevice device;
  struct Record { Request req; std::shared_ptr<PuDExecutionContext> context; };
  std::vector<Record> records;
  std::vector<PuDOccurrence> saved;
};

// W4 drives the same ControllerBase buffers/retirement/completion inherited by
// GenericDDR. Scheduling and footprint reservation are explicit fixture actions;
// no production allocator/arbitration is supplied by this test.
class ComputeLifecycleUnderTest : public ControllerBase {
 public:
  explicit ComputeLifecycleUnderTest(nb::dict config)
      : ControllerBase(py_to_confignode(config), nullptr) {
    IController::m_impl = this;
    init_base();
    set_channel_id(0);
    HarnessFrontEnd frontend(1);
    setup_base(&frontend, nullptr);
  }
  std::string get_name() const override { return "ComputeLifecycleFixture"; }
  std::string get_ifce_name() const override { return "controller"; }
  void init() override {}
  void tick() override { tick_prologue(); }
  void advance(Clk_t clk) {
    if (clk < m_clk) throw std::logic_error("fixture clock cannot go backwards");
    while (m_clk < clk) tick();
    serve_completed_requests();
  }
  bool add(Request req, int source, nb::object callback) {
    initialize_pud_sequence(req, *m_device.m_spec);
    req.source_id = source;
    req.arrive = m_clk;
    req.callback = [this, callback](Request& completed) {
      nb::dict event = located_snapshot(completed, false);
      event["source"] = completed.source_id;
      event["arrive"] = completed.arrive;
      event["depart"] = completed.depart;
      event["callback_clk"] = m_clk;
      event["context_expired"] = completed.pud_context.expired();
      event["stats"] = snapshot();
      events.append(event);
      if (!callback.is_none()) callback(event);
    };
    if (!m_pud_buffer.enqueue(req)) return false;
    ++s_num_pud_reqs[*legacy_pud_statistic_slot(req.type_id)];
    return true;
  }
  bool reserve(int source) {
    auto [buffer, it] = find(source);
    return reserve_pud_compute(*it);
  }
  bool available(const Request& req) const {
    return pud_compute_resources_available(req);
  }
  void dispatch(int source, Clk_t clk, bool coincident_terminal, Clk_t retirement_delay) {
    advance(clk);
    auto [buffer, it] = find(source);
    auto& context = protected_pud_context(*it);
    const auto occurrence = describe_pud_occurrence(*it, it->occurrence_index, *m_device.m_spec);
    // A synthetic completion-queue tie fixture may give two terminal PREs the
    // same clock. This tests simultaneous recovery release, not C/A scheduling.
    if (clk <= last_issue && !(coincident_terminal && occurrence.terminal && clk == last_issue)) {
      throw std::logic_error("fixture C/A slot occupied");
    }
    if (coincident_terminal && occurrence.terminal && clk == last_issue) {
      // Synthetic equal-deadline fixture only: bypass the occupied issue cycle,
      // while keeping the same Device occurrence, phase and timing checks.
      m_device.m_pud_resource_ready[0] = clk;
    }
    it->command = occurrence.command;
    m_device.issue_pud_command(*it, occurrence, &context, m_clk);
    last_issue = clk;
    if (occurrence.terminal) {
      // Diagnostic fixture only: distinguish issue time from retirement time.
      // Normal controller sequencing retires immediately at terminal PRE.
      if (retirement_delay != 0) advance(clk + retirement_delay);
      retire_request(it, *buffer);
    } else if (buffer != &m_active_buffer) {
      promote_to_active(it, *buffer);
    }
  }
  void capacity(size_t pending, size_t active) {
    m_pud_buffer.max_size = pending;
    m_active_buffer.max_size = active;
  }
  size_t save(int source) {
    auto [buffer, it] = find(source);
    saved.push_back(*it);
    return saved.size() - 1;
  }
  bool saved_expired(size_t id) const { return saved.at(id).pud_context.expired(); }
  bool reserve_saved(size_t id) { return reserve_pud_compute(saved.at(id)); }
  void stale_dispatch(size_t id) {
    auto req = saved.at(id);
    auto& context = protected_pud_context(req);
    const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, *m_device.m_spec);
    m_device.issue_pud_command(req, occurrence, &context, m_clk);
  }
  void retire_copy(int source) {
    Request req;
    auto pending = std::find_if(m_pending.begin(), m_pending.end(),
        [&](const Request& r) { return r.source_id == source; });
    if (pending != m_pending.end()) req = *pending;
    else req = *find(source).second;
    ReqBuffer copy;
    copy.enqueue(req);
    auto it = copy.begin();
    retire_request(it, copy);
  }
  // Real ordinary retirement and forwarding, without mixed-traffic scheduling.
  void retire_read(int source, Clk_t clk) {
    advance(clk);
    Request req(AddrVec_t{0, 0, 0, 1, 10, 0}, Request::Type::Read);
    req.source_id = source;
    req.arrive = m_clk;
    req.callback = [this](Request& r) {
      nb::dict event;
      event["source"] = r.source_id;
      event["depart"] = r.depart;
      event["callback_clk"] = m_clk;
      events.append(event);
    };
    m_read_buffer.enqueue(req);
    ++s_num_read_reqs;
    auto it = m_read_buffer.begin();
    retire_request(it, m_read_buffer);
  }
  void forwarded_read(int source) {
    Request write(AddrVec_t{0, 0, 0, 1, 11, 0}, Request::Type::Write);
    write.addr = 1234;
    if (!send(write)) throw std::logic_error("fixture write enqueue failed");
    Request read(write.addr_vec, Request::Type::Read);
    read.addr = write.addr;
    read.source_id = source;
    read.callback = [this](Request& r) {
      nb::dict event;
      event["source"] = r.source_id;
      event["depart"] = r.depart;
      event["callback_clk"] = m_clk;
      events.append(event);
    };
    if (!send(read) || read.depart != m_clk + 1) throw std::logic_error("fixture read not forwarded");
    auto it = m_write_buffer.begin();
    retire_request(it, m_write_buffer);
  }
  nb::dict state(int source) {
    auto [buffer, it] = find(source);
    return located_snapshot(*it, false);
  }
  nb::dict snapshot() {
    nb::dict out;
    out["clk"] = m_clk;
    out["pending"] = m_pud_buffer.size();
    out["active"] = m_active_buffer.size();
    out["active_per_bank"] = m_active_per_bank;
    out["delayed"] = m_pending.size();
    out["device_context_references"] = m_device.m_protected_pud.size();
    out["rw_buffered"] = m_read_buffer.size() + m_write_buffer.size();
    nb::list held;
    for (const auto& record : m_protected_pud) {
      nb::dict item;
      auto identify = [&](const auto& requests) {
        for (const auto& req : requests) {
          if (req.pud_context.lock() == record.context) item["source"] = req.source_id;
        }
      };
      identify(m_pud_buffer.buffer);
      identify(m_active_buffer.buffer);
      identify(m_pending);
      item["phase"] = static_cast<int>(record.context->phase());
      const auto pending = std::find_if(m_pending.begin(), m_pending.end(),
          [&](const Request& req) { return req.pud_context.lock() == record.context; });
      item["depart"] = pending == m_pending.end() ? nb::none() : nb::cast(pending->depart);
      item["completion_pending"] = record.completion_pending;
      held.append(item);
    }
    out["held"] = held;
    update_stats();
    out["counters"] = confignode_to_py(IController::collect_stats());
    return out;
  }
  nb::list completions() const { return events; }

 private:
  std::pair<ReqBuffer*, ReqBuffer::iterator> find(int source) {
    for (auto* buffer : {&m_pud_buffer, &m_active_buffer}) {
      auto it = std::find_if(buffer->begin(), buffer->end(),
          [&](const Request& req) { return req.source_id == source; });
      if (it != buffer->end()) return {buffer, it};
    }
    throw std::logic_error("fixture invocation is not schedulable");
  }
  Clk_t last_issue = -1;
  std::vector<Request> saved;
  nb::list events;
};

// W5 uses the real GenericDDR scheduler for legacy/ordinary/maintenance traffic.
// Compute reservations/occurrences remain explicit fixture actions, outside
// public ingress and allocation/arbitration policy.
namespace Ramulator {
class PuDConflictUnderTest {
 public:
  // W6's explicit-reservation fixture uses sources 0..11; W7 uses 0..8.
  explicit PuDConflictUnderTest(nb::dict config) : dut(config, 12, false), ctrl(dut.m_controller_base) {}
  // W7 only: bypass public ingress, but exercise the real GenericDDR buffer,
  // allocator, arbitration and completion. No fixture footprint assignment.
  bool enqueue(Request req, int source, nb::object callback) {
    check_source(source);
    if (!req.pud_locations || !is_inherited_pud_request_type(req.type_id)) {
      throw std::logic_error("W7 fixture enqueue requires located compute");
    }
    validate_pud_placement(req, *ctrl->m_device.m_spec, 0,
                           get_pud_placement_levels(*ctrl->m_device.m_spec));
    initialize_pud_sequence(req, *ctrl->m_device.m_spec);
    req.source_id = source;
    req.arrive = ctrl->m_clk;
    req.callback = [this, callback](Request& r) {
      nb::dict event = located_snapshot(r, false);
      event["source"] = r.source_id;
      event["depart"] = r.depart;
      event["held"] = held();
      event["stats"] = stats();
      completed.append(event);
      if (!callback.is_none()) callback(event);
    };
    if (!ctrl->m_pud_buffer.enqueue(req)) return false;
    ctrl->s_num_pud_reqs[*legacy_pud_statistic_slot(req.type_id)]++;
    dut.m_command_outstanding++;
    return true;
  }
  nb::dict scheduling() const {
    nb::dict out;
    std::vector<int> unallocated, allocated, recovering;
    for (const auto& req : ctrl->m_pud_buffer.buffer) {
      if (!req.pud_locations || !is_inherited_pud_request_type(req.type_id)) continue;
      (req.pud_context.expired() ? unallocated : allocated).push_back(req.source_id);
    }
    for (const auto& req : ctrl->m_pending) {
      if (req.pud_locations && is_inherited_pud_request_type(req.type_id)) recovering.push_back(req.source_id);
    }
    out["unallocated"] = unallocated;
    out["allocated"] = allocated;
    out["recovering"] = recovering;
    out["active_size"] = ctrl->m_active_buffer.size();
    out["pud_size"] = ctrl->m_pud_buffer.size();
    return out;
  }
  bool scheduled_probe(int source) {
    return ctrl->check_request_timing(find_compute(source));
  }
  bool allocation_probe(Request req) const {
    initialize_pud_sequence(req, *ctrl->m_device.m_spec);
    return ctrl->pud_compute_resources_available(req) && ctrl->pud_compute_start_eligible(req);
  }
  void block_command_bus(Clk_t until) { ctrl->m_device.m_command_resource_ready[0] = until; }
  // Interpose for one real tick after selection, without a production hook.
  void recheck_tick(const std::string& command, nb::object callback) {
    struct Upgrade final : IRowPolicy {
      IRowPolicy* original;
      std::function<void(Request&)> change;
      void pre_schedule() override { original->pre_schedule(); }
      void try_upgrade_command(Request& req) override { original->try_upgrade_command(req); change(req); }
      void on_issue(const Request& req) override { original->on_issue(req); }
      void post_schedule() override { original->post_schedule(); }
    } upgrade;
    upgrade.original = ctrl->m_rowpolicy;
    upgrade.change = [&](Request& req) {
      if (!command.empty()) req.command = ctrl->m_device.m_spec->get_command_id(command);
      if (!callback.is_none()) callback();
    };
    ctrl->m_rowpolicy = &upgrade;
    try {
      advance(ctrl->m_clk + 1);
    } catch (...) {
      ctrl->m_rowpolicy = upgrade.original;
      throw;
    }
    ctrl->m_rowpolicy = upgrade.original;
  }
  bool add(Request req, int source) {
    check_source(source);
    initialize_pud_sequence(req, *ctrl->m_device.m_spec);
    req.source_id = source;
    req.arrive = ctrl->m_clk;
    if (!ctrl->reserve_pud_compute(req)) return false;
    req.callback = [this](Request& r) {
      nb::dict event = located_snapshot(r, false);
      event["source"] = r.source_id;
      event["depart"] = r.depart;
      completed.append(event);
    };
    compute.emplace(source, std::move(req));
    return true;
  }
  bool start(Request req) const {
    initialize_pud_sequence(req, *ctrl->m_device.m_spec);
    return ctrl->pud_compute_start_eligible(req);
  }
  void dispatch(int source, Clk_t clk) {
    advance(clk);
    compute_dispatch(source, true);
  }
  void advance(Clk_t clk) {
    if (clk < ctrl->m_clk) throw std::logic_error("fixture clock cannot go backwards");
    while (ctrl->m_clk < clk) {
      for (auto event : dut.tick()) {
        history.append(event);
      }
    }
  }
  void movement(Request req, int source) {
    check_source(source);
    validate_pud_placement(req, *ctrl->m_device.m_spec, 0,
                           get_pud_placement_levels(*ctrl->m_device.m_spec));
    req.source_id = source;
    req.callback = [this](Request& r) {
      nb::dict event = movement_snapshot(r);
      event["source"] = r.source_id;
      event["depart"] = r.depart;
      completed.append(event);
    };
    if (!ctrl->try_send_special_request(req).value()) throw std::logic_error("fixture movement enqueue failed");
  }
  nb::dict movement_state(int source) const {
    for (const auto* buffer : {&ctrl->m_pud_buffer, &ctrl->m_active_buffer}) {
      for (const auto& req : buffer->buffer) {
        if (req.source_id == source) return movement_snapshot(req);
      }
    }
    for (const auto& req : ctrl->m_pending) {
      if (req.source_id == source) return movement_snapshot(req);
    }
    throw std::logic_error("fixture movement not retained");
  }
  void send(int type, const AddrVec_t& addr, int source) {
    check_source(source);
    dut.send_request(type, addr, source);
  }
  void priority(const std::string& command, const AddrVec_t& addr) { dut.priority_send(command, addr); }
  nb::dict probe(const std::string& final, const std::string& command, const AddrVec_t& addr) {
    const auto& spec = *ctrl->m_device.m_spec;
    Request req(addr, Request::Cmd, spec.get_command_id(final));
    req.command = spec.get_command_id(command);
    nb::dict out;
    const bool eligible = ctrl->is_pud_eligible_before_prerequisite(req);
    out["eligible"] = eligible;
    out["close"] = ctrl->would_close_active(req);
    out["preq"] = eligible ? nb::cast(spec.command_names[ctrl->get_preq_command(req.final_command, addr)]) : nb::none();
    out["issue"] = ctrl->validate_request_for_issue(req);
    return out;
  }
  void raw(const std::string& command, const AddrVec_t& addr, bool issue) {
    auto& device = ctrl->m_device;
    int cmd = device.m_spec->get_command_id(command);
    if (issue) device.issue_command(cmd, addr, ctrl->m_clk);
    else device.get_preq_command(cmd, addr, ctrl->m_clk);
  }
  nb::list shared() const {
    nb::list out;
    auto& device = ctrl->m_device;
    for (int level = 0; level <= device.m_bank_level; ++level) {
      device.m_root->for_each_at_level(level, [&](DRAMNode* node) {
        nb::dict item;
        item["state"] = node->m_state;
        item["rows"] = std::map<int, int>(node->m_row_state.begin(), node->m_row_state.end());
        item["ready"] = node->m_cmd_ready_clk;
        std::vector<std::vector<Clk_t>> histories;
        for (const auto& h : node->m_cmd_history) histories.emplace_back(h.begin(), h.end());
        item["history"] = histories;
        out.append(item);
      });
    }
    return out;
  }
  nb::list issued() const { return history; }
  nb::list completions() const { return completed; }
  // Count protected compute invocations, including fixture-driven requests.
  size_t held() const {
    return std::count_if(ctrl->m_protected_pud.begin(), ctrl->m_protected_pud.end(),
        [&](const auto& held) {
          for (const auto& [source, req] : compute) {
            if (req.pud_context.lock() == held.context) return true;
          }
          auto contains = [&](const auto& requests) {
            return std::any_of(requests.begin(), requests.end(), [&](const Request& req) {
              return is_inherited_pud_request_type(req.type_id) &&
                     req.pud_context.lock() == held.context;
            });
          };
          return contains(ctrl->m_pud_buffer.buffer) || contains(ctrl->m_active_buffer.buffer) ||
                 contains(ctrl->m_pending);
        });
  }
  nb::dict stats() { ctrl->update_stats(); return nb::cast<nb::dict>(confignode_to_py(ctrl->IController::collect_stats())); }
  void capacity(size_t active) { ctrl->m_active_buffer.max_size = active; }

  // Exercise the production issue path with explicit fixture reservations.
  bool compute_dispatch(int source, bool issue) {
    auto& req = compute.at(source);
    const bool ready = ctrl->check_pud_compute_issue(req);
    if (!issue) return ready;
    if (!ready) throw std::logic_error("Compute issue timing or eligibility not ready");
    const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, *ctrl->m_device.m_spec);
    ctrl->issue_pud_compute(req);
    // Relocate the sole schedulable Request, retaining its resolved association.
    Request copied = req;
    req = std::move(copied);
    if (occurrence.terminal) retire_compute(req);
    return true;
  }
  nb::dict compute_state(int source) const {
    const auto& req = find_compute(source);
    auto out = located_snapshot(req, false);
    const auto context = req.pud_context.lock();
    out["phase"] = context ? static_cast<int>(context->phase()) : -1;
    nb::list occurrences;
    // Observation derived from the sole Request history, not retained target state.
    for (size_t i = 0; i < get_pud_sequence_length(req); ++i) {
      const auto occurrence = describe_pud_occurrence(req, i, *ctrl->m_device.m_spec);
      const auto& origin = occurrence.location()->location.origin;
      nb::dict item;
      item["index"] = i;
      item["command"] = ctrl->m_device.m_spec->command_names[occurrence.command];
      item["operand"] = occurrence.operand_index;
      item["external"] = occurrence.location()->external;
      auto coordinates = origin.bank;
      coordinates.insert(coordinates.end(), {origin.subarray, origin.local_row});
      item["origin"] = coordinates;
      item["range"] = std::vector<int>{origin.mats.first, origin.mats.last};
      item["associated"] = context && occurrence.locations == context->locations();
      item["issued"] = req.occurrence_issue_history.at(i);
      std::vector<std::vector<int>> segments;
      for (const auto& segment : req.pud_locations->resolver->segment_range(origin.mats)) {
        segments.push_back({segment.chip, segment.first_local_mat, segment.last_local_mat});
      }
      item["segments"] = segments;
      occurrences.append(item);
    }
    out["occurrences"] = occurrences;
    return out;
  }
  bool unallocated_dispatch(Request req, bool issue) {
    initialize_pud_sequence(req, *ctrl->m_device.m_spec);
    if (!issue) return ctrl->check_pud_compute_issue(req);
    ctrl->issue_pud_compute(req);
    return true;
  }
  std::vector<Clk_t> command_occupancy() const {
    return {ddr4_test_deadline(ctrl->m_device.m_pud_resource_ready),
            ddr4_test_deadline(ctrl->m_device.m_command_resource_ready)};
  }

 private:
  const Request& find_compute(int source) const {
    if (const auto it = compute.find(source); it != compute.end()) return it->second;
    for (const auto& req : ctrl->m_pud_buffer.buffer) if (req.source_id == source) return req;
    for (const auto& req : ctrl->m_pending) if (req.source_id == source) return req;
    throw std::logic_error("fixture compute not retained");
  }
  void retire_compute(Request& req) {
    ReqBuffer retiring;
    retiring.enqueue(req);
    auto it = retiring.begin();
    ctrl->retire_request(it, retiring);
  }
  static nb::dict movement_snapshot(const Request& req) {
    auto out = located_snapshot(req, false);
    auto state = describe_pud_movement_state(req);
    out["source_active"] = state.source_active;
    out["destination_active"] = state.destination_active;
    out["source_valid"] = state.source_valid;
    out["sequence_active"] = state.sequence_active;
    return out;
  }
  ControllerUnderTestCpp dut;
  void check_source(int source) const {
    if (source < 0 || source >= dut.m_frontend->get_num_cores()) {
      throw std::invalid_argument("invalid fixture source_id");
    }
  }
  ControllerBase* ctrl;
  std::map<int, Request> compute;
  nb::list history;
  nb::list completed;
};

}  // namespace Ramulator

inline void bind_pud_request_harness(nb::module_& m) {
  nb::class_<PuDConflictUnderTest>(m, "_PuDConflictUnderTest")
      .def(nb::init<nb::dict>())
      .def("enqueue", &PuDConflictUnderTest::enqueue, nb::arg("req"), nb::arg("source"), nb::arg("callback") = nb::none())
      .def("scheduling", &PuDConflictUnderTest::scheduling)
      .def("scheduled_probe", &PuDConflictUnderTest::scheduled_probe)
      .def("allocation_probe", &PuDConflictUnderTest::allocation_probe)
      .def("block_command_bus", &PuDConflictUnderTest::block_command_bus)
      .def("recheck_tick", &PuDConflictUnderTest::recheck_tick,
           nb::arg("command") = "", nb::arg("callback") = nb::none())
      .def("add", &PuDConflictUnderTest::add)
      .def("start", &PuDConflictUnderTest::start)
      .def("dispatch", &PuDConflictUnderTest::dispatch)
      .def("advance", &PuDConflictUnderTest::advance)
      .def("movement", &PuDConflictUnderTest::movement)
      .def("movement_state", &PuDConflictUnderTest::movement_state)
      .def("send", &PuDConflictUnderTest::send)
      .def("priority", &PuDConflictUnderTest::priority)
      .def("probe", &PuDConflictUnderTest::probe)
      .def("raw", &PuDConflictUnderTest::raw)
      .def("shared", &PuDConflictUnderTest::shared)
      .def("issued", &PuDConflictUnderTest::issued)
      .def("completions", &PuDConflictUnderTest::completions)
      .def("held", &PuDConflictUnderTest::held)
      .def("stats", &PuDConflictUnderTest::stats)
      .def("capacity", &PuDConflictUnderTest::capacity)
      .def("compute_dispatch", &PuDConflictUnderTest::compute_dispatch, nb::arg("source"), nb::arg("issue") = false)
      .def("unallocated_dispatch", &PuDConflictUnderTest::unallocated_dispatch)
      .def("compute_state", &PuDConflictUnderTest::compute_state)
      .def("command_occupancy", &PuDConflictUnderTest::command_occupancy);
  nb::class_<ComputeLifecycleUnderTest>(m, "_ComputeLifecycleUnderTest")
      .def(nb::init<nb::dict>())
      .def("add", &ComputeLifecycleUnderTest::add, nb::arg("req"), nb::arg("source"),
           nb::arg("callback") = nb::none())
      .def("reserve", &ComputeLifecycleUnderTest::reserve)
      .def("available", &ComputeLifecycleUnderTest::available)
      .def("dispatch", &ComputeLifecycleUnderTest::dispatch, nb::arg("source"), nb::arg("clk"),
           nb::arg("coincident_terminal") = false, nb::arg("retirement_delay") = 0)
      .def("advance", &ComputeLifecycleUnderTest::advance)
      .def("capacity", &ComputeLifecycleUnderTest::capacity)
      .def("save", &ComputeLifecycleUnderTest::save)
      .def("saved_expired", &ComputeLifecycleUnderTest::saved_expired)
      .def("reserve_saved", &ComputeLifecycleUnderTest::reserve_saved)
      .def("stale_dispatch", &ComputeLifecycleUnderTest::stale_dispatch)
      .def("retire_copy", &ComputeLifecycleUnderTest::retire_copy)
      .def("retire_read", &ComputeLifecycleUnderTest::retire_read)
      .def("forwarded_read", &ComputeLifecycleUnderTest::forwarded_read)
      .def("state", &ComputeLifecycleUnderTest::state)
      .def("snapshot", &ComputeLifecycleUnderTest::snapshot)
      .def("completions", &ComputeLifecycleUnderTest::completions);
  nb::class_<ComputeRangesUnderTest>(m, "_ComputeRangesUnderTest")
      .def(nb::init<nb::dict>())
      .def("add", &ComputeRangesUnderTest::add)
      .def("save", &ComputeRangesUnderTest::save)
      .def("corrupt_occurrence", &ComputeRangesUnderTest::corrupt_occurrence)
      .def("dispatch", &ComputeRangesUnderTest::dispatch, nb::arg("id"), nb::arg("clk"),
           nb::arg("issue") = false, nb::arg("context_id") = -1, nb::arg("saved_occurrence") = -1,
           nb::arg("command") = "", nb::arg("foreign_device") = false)
      .def("state", &ComputeRangesUnderTest::state, nb::arg("id"))
      .def("shared", &ComputeRangesUnderTest::shared)
      .def("raw", &ComputeRangesUnderTest::raw, nb::arg("command"), nb::arg("addr"), nb::arg("clk"),
           nb::arg("issue") = false)
      .def("skip", &ComputeRangesUnderTest::skip);
  nb::class_<Request>(m, "_LocatedRequest")
      .def("copy", [](const Request& req) { return Request(req); })
      .def("snapshot", &located_snapshot, nb::arg("cells") = false)
      .def_rw("operands", &Request::operands)
      .def_rw("addr_vec", &Request::addr_vec)
      .def_rw("size_bytes", &Request::size_bytes)
      .def_rw("type_id", &Request::type_id);
  m.def("_located_request", &located_request);
  m.def("_bare_request", [](int type, std::vector<AddrVec_t> operands, int size) {
    // Deliberately bypass the public ordered-operand constructor so negative
    // ingress tests can probe malformed legacy-shaped compute Requests.
    Request req;
    req.type_id = type;
    req.operands = std::move(operands);
    req.size_bytes = size;
    return req;
  });
  m.def("_construct_bare_request", [](int type, std::vector<AddrVec_t> operands) {
    return Request(std::move(operands), type);
  });
  m.def("_tamper_location", [](Request req, const std::string& field) {
    auto copy = std::make_shared<PuD::RequestLocations>(*req.pud_locations);
    auto& pair = copy->operands.front();
    if (field == "association") {
      pair.location.association = std::make_shared<const PuD::LocationAssociation>(*pair.location.association);
    } else if (field == "missing_origin") {
      pair.location.association.reset();
    } else if (field == "external_row") {
      pair.location.external_row.row++;
    } else if (field == "burst") {
      pair.location.burst = PuD::BurstColumn{127};
    } else if (field == "cell_count") {
      pair.location.cell_count++;
    } else if (field == "range") {
      pair.location.origin.mats.last++;
    } else if (field == "missing_resolver") {
      copy->resolver.reset();
    } else if (field == "count") {
      copy->operands.pop_back();
    } else if (field == "legacy_metadata") {
      req.movement = Request::LCMovementMetadata{{0, 0}};
    } else {
      throw std::invalid_argument("unknown corruption");
    }
    req.pud_locations = copy;
    return req;
  });
  m.def(
      "_validate_located_request",
      [](const LocationResolverUnderTest& fixture, const Request& req, nb::dict dram, int channel, bool placement) {
        int route = validate_pud_routing(req, 1);
        auto cfg = py_to_confignode(dram);
        auto spec = DRAMSpec::create(cfg["impl"].as<std::string>(), ConfigNode(ConfigNode::Map{{"dram", cfg}}));
        if (placement) {
          validate_pud_placement(req, *spec, channel, get_pud_placement_levels(*spec), fixture.resolver().get());
        }
        nb::dict out;
        out["route"] = route;
        if (placement && is_movement_request_type(req.type_id)) {
          out["bits"] = get_movement_moved_bits(req, *spec);
        }
        return out;
      },
      nb::arg("resolver"), nb::arg("request"), nb::arg("dram"), nb::arg("channel") = 0, nb::arg("placement") = true);
  m.def("_located_lifetime", [](Request req, nb::dict dram) {
    auto cfg = py_to_confignode(dram);
    auto spec = DRAMSpec::create(cfg["impl"].as<std::string>(), ConfigNode(ConfigNode::Map{{"dram", cfg}}));
    validate_pud_placement(req, *spec, 0, get_pud_placement_levels(*spec));
    initialize_pud_sequence(req, *spec);
    ReqBuffer pending(0);
    nb::dict out;
    auto identity = req.pud_locations;
    out["failed_enqueue"] = !pending.enqueue(req);
    pending.max_size = 1;
    out["retry"] = pending.enqueue(req);
    req = Request{};  // Destroy the submitting copy.
    Request active = pending.buffer.front();
    pending.buffer.clear();
    auto before = active.occurrence_issue_history;
    out["prerequisite_unchanged"] =
        observe_pud_command_issue(active, spec->get_command_id("PREpb"), 0, *spec) == PuDOccurrenceAdvance::NotIssued &&
        active.occurrence_issue_history == before && active.occurrence_index == 0;
    nb::list occurrences;
    std::vector<PuDOccurrence> retained;
    nb::list movement_states;
    bool same_bundle = active.pud_locations == identity;
    while (active.occurrence_index < get_pud_sequence_length(active)) {
      const auto occurrence = describe_pud_occurrence(active, active.occurrence_index, *spec);
      nb::dict item;
      item["operand"] = occurrence.operand_index;
      item["command"] = spec->command_names[occurrence.command];
      item["external"] = occurrence.location()->external;
      item["range"] = std::vector<int>{occurrence.location()->location.origin.mats.first,
                                       occurrence.location()->location.origin.mats.last};
      occurrences.append(item);
      retained.push_back(occurrence);
      observe_pud_command_issue(active, active.final_command, active.occurrence_index + 1, *spec);
      ReqBuffer copied;
      copied.enqueue(active);
      active = copied.buffer.front();
      same_bundle &= active.pud_locations == identity;
      if (is_movement_request_type(active.type_id)) {
        const auto state = describe_pud_movement_state(active);
        nb::dict snapshot = located_snapshot(active, false);
        snapshot["source_active"] = state.source_active;
        snapshot["destination_active"] = state.destination_active;
        snapshot["source_valid"] = state.source_valid;
        snapshot["same_bundle"] = state.locations == identity;
        movement_states.append(snapshot);
      }
    }
    // The existing pending completion container/copy shape, without executing
    // a v2 command or inventing any W3+ temporal state.
    std::deque<Request> completions;
    active.callback = [&](Request& completed) { out["completion"] = located_snapshot(completed, false); };
    completions.push_back(active);
    active = Request{};
    Request completed = std::move(completions.front());
    completions.pop_front();
    completed.callback(completed);
    completed = Request{};
    out["same_bundle"] = same_bundle;
    out["occurrences"] = occurrences;
    out["movement_states"] = movement_states;
    out["descriptor_survives"] = retained.back().locations == identity && retained.back().location() != nullptr;
    return out;
  });
  nb::class_<LocatedSystemUnderTest>(m, "_LocatedSystemUnderTest")
      .def(nb::init<nb::dict, const LocationResolverUnderTest&, const std::string&, bool>(), nb::arg("controller"),
           nb::arg("resolver"), nb::arg("channel_mapper") = "CacheLineInterleave", nb::arg("install") = true)
      .def("send", &LocatedSystemUnderTest::send, nb::arg("request"), nb::arg("path") = "system")
      .def("request", &LocatedSystemUnderTest::request)
      .def("submit", &LocatedSystemUnderTest::submit, nb::arg("request"), nb::arg("source"), nb::arg("callback") = nb::none())
      .def("submit_ordinary", &LocatedSystemUnderTest::submit_ordinary)
      .def("advance", &LocatedSystemUnderTest::advance)
      .def("issued", &LocatedSystemUnderTest::issued)
      .def("completions", &LocatedSystemUnderTest::completions)
      .def("scheduling", &LocatedSystemUnderTest::scheduling)
      .def("ordinary", &LocatedSystemUnderTest::ordinary, nb::arg("address"), nb::arg("type"), nb::arg("size") = 1,
           nb::arg("cells") = true, nb::arg("wrong_intra") = nb::none())
      .def("stats", &LocatedSystemUnderTest::stats)
      .def("forwarding", &LocatedSystemUnderTest::forwarding)
      .def_prop_ro("pending", &LocatedSystemUnderTest::pending);
}

#endif
