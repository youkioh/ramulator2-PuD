#ifndef RAMULATOR_TESTS_PUD_REQUEST_HARNESS_H
#define RAMULATOR_TESTS_PUD_REQUEST_HARNESS_H

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
      item["origin"] = std::vector<int>{o.channel, o.rank, o.bank_group, o.bank, o.subarray, o.local_row};
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
      if (name != "kind" && name != "row" && name != "range" && name != "group" && name != "column") {
        throw std::invalid_argument("unsupported region descriptor");
      }
    }
    if (!d.contains("range")) {
      throw std::invalid_argument("explicit range required");
    }
    auto mats = nb::cast<std::vector<int>>(d["range"]);
    if (mats.size() != 2) {
      throw std::invalid_argument("one inclusive contiguous range required");
    }
    auto row = nb::cast<std::vector<int>>(d["row"]);
    auto kind = nb::cast<std::string>(d["kind"]);
    if (kind != "compute" && kind != "group" && kind != "layout") {
      throw std::invalid_argument("PuD operand requires an explicit layout region, not a bit anchor");
    }
    std::optional<int> group;
    if (d.contains("group")) {
      group = nb::cast<int>(d["group"]);
    }
    std::optional<PuD::BurstColumn> column;
    if (d.contains("column")) {
      column = PuD::BurstColumn{nb::cast<int>(d["column"])};
    }
    operands.push_back(fixture.resolver()->pair(fixture.region(kind, row, mats[0], mats[1], group), column));
  }
  Request req(fixture.resolver(), std::move(operands), type);
  req.size_bytes = size;
  return req;
}

// Capture the actual GenericDDR instance while constructing a real GenericDRAM
// system; no production controller discovery API is needed for these tests.
class LocationHarnessObserver final : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin, LocationHarnessObserver, "LocationHarnessObserver");

 public:
  inline static ControllerBase* created_controller = nullptr;
  void init() override {
    created_controller = cast_parent<ControllerBase>();
  }
};

class LocatedSystemUnderTest {
 public:
  LocatedSystemUnderTest(nb::dict controller, const LocationResolverUnderTest& fixture,
                         const std::string& channel_mapper, bool install)
      : m_frontend(std::make_unique<HarnessFrontEnd>(1)), m_resolver(fixture.resolver()) {
    auto config = py_to_confignode(controller);
    config.set("controller_plugins", ConfigNode::Seq{ConfigNode::Map{{"impl", "LocationHarnessObserver"}}});
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
    if (install) {
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
  nb::dict ordinary(Addr_t address, int type, int size, bool cells, std::optional<Addr_t> wrong_intra) {
    Request req(address, type);
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
    return nb::cast<nb::dict>(confignode_to_py(m_system->collect_stats()));
  }
  nb::dict forwarding() {
    int callbacks = 0;
    bool retained = false;
    for (int type : {Request::Type::Write, Request::Type::Write, Request::Type::Read}) {
      Request req(7, type);
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
};

// W3 component-only execution: fixtures provide separate ranges directly. No
// production scheduler, target transport, engine or completion is installed.
class ComputeRangesUnderTest {
 public:
  explicit ComputeRangesUnderTest(nb::dict dram) {
    auto cfg = py_to_confignode(dram);
    device.init(DRAMSpec::create(cfg["impl"].as<std::string>(), ConfigNode(ConfigNode::Map{{"dram", cfg}})));
  }
  size_t add(Request req) {
    initialize_pud_sequence(req, *device.m_spec);
    auto context = device.make_pud_compute_context(req);
    records.push_back({std::move(req), std::move(context)});
    return records.size() - 1;
  }
  size_t save(size_t id) {
    const auto& req = records.at(id).req;
    saved.push_back({req, describe_pud_occurrence(req, req.occurrence_index, *device.m_spec)});
    return saved.size() - 1;
  }
  void corrupt_descriptor(size_t id, const std::string& field) {
    auto& occurrence = saved.at(id).second;
    if (field == "wrong_operand") occurrence.operand_index ^= 1;
    else if (field == "wrong_index") ++occurrence.index;
    else if (field == "terminal") occurrence.terminal = !occurrence.terminal;
    else if (field == "unassociated") occurrence.locations.reset();
    else throw std::invalid_argument("unknown descriptor corruption");
  }
  bool dispatch(size_t id, Clk_t clk, bool issue, int context_id, int descriptor,
                const std::string& command, bool stale_request, bool foreign_device) {
    auto& record = records.at(id);
    auto& req = stale_request ? saved.at(descriptor).first : record.req;
    auto occurrence = descriptor < 0 ? describe_pud_occurrence(req, req.occurrence_index, *device.m_spec)
                                     : saved.at(descriptor).second;
    if (!command.empty()) occurrence.command = device.m_spec->get_command_id(command);
    auto* context = context_id == -2 ? nullptr : records.at(context_id < 0 ? id : context_id).context.get();
    // A second Device rejects a context minted by the first before any access.
    DRAMDevice other;
    auto& target = foreign_device ? other : device;
    const bool ready = target.check_pud_timing(req, occurrence, context, clk) && clk > last_shared_issue;
    if (!issue) return ready;
    if (!ready) throw std::logic_error("Compute range timing not ready (fixture C/A issue slot)");
    target.issue_pud_command(req, occurrence, context, clk);
    last_shared_issue = clk;
    // Exercise Request relocation after every action, retaining one cursor.
    Request copied = req;
    req = std::move(copied);
    return true;
  }
  nb::dict state(size_t id, Clk_t clk) const {
    const auto& record = records.at(id);
    const auto& context = *record.context;
    nb::dict out = located_snapshot(record.req, false);
    static const char* phases[] = {"Closed", "PuDChargeSharing", "PuDSensed", "Recovering"};
    out["phase"] = phases[static_cast<int>(context.phase())];
    out["activated_operands"] = context.activated_operands();
    std::vector<AddrVec_t> rows;
    for (auto operand : context.activated_operands()) rows.push_back(context.locations()->operands[operand].external);
    out["activated_rows"] = rows;
    out["last_issue"] = context.last_issue_clk();
    out["recovery_clk"] = context.recovery_ready_clk();
    out["recovery_ready"] = context.recovery_ready(clk);
    out["same_bundle"] = record.req.pud_locations == context.locations();
    return out;
  }
  nb::list shared() const {
    nb::list out;
    for (int level = 0; level <= device.m_bank_level; ++level) {
      device.m_root->for_each_at_level(level, [&](DRAMNode* node) {
        nb::dict item;
        item["level"] = level;
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
    bool ready = device.get_preq_command(cmd, addr, clk) == cmd && device.check_timing(cmd, addr, clk) &&
                 clk > last_shared_issue;
    if (issue) {
      if (!ready) throw std::logic_error("raw fixture command not ready");
      device.issue_command(cmd, addr, clk);
      last_shared_issue = clk;
    }
    return ready;
  }
  void skip(size_t id) {
    auto& req = records.at(id).req;
    observe_pud_command_issue(req, req.final_command, 123, *device.m_spec);
  }

 private:
  DRAMDevice device;
  // Mirror the existing controller's one-command-per-tick arbitration only.
  // DDR4 intentionally generates no Device C/A edge for a one-tick command.
  Clk_t last_shared_issue = -1;
  struct Record { Request req; std::unique_ptr<PuDComputeContext> context; };
  std::vector<Record> records;
  std::vector<std::pair<Request, PuDOccurrence>> saved;
};

// W4 drives the same ControllerBase buffers/retirement/completion inherited by
// GenericDDR. Scheduling and allocation are explicit fixture actions: no W5
// exclusion, W6 transport or W7 allocator/arbitration is supplied by this test.
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
      event["context_expired"] = completed.pud_compute_context.expired();
      event["stats"] = snapshot();
      events.append(event);
      if (!callback.is_none()) callback(event);
    };
    if (!m_pud_buffer.enqueue(req)) return false;
    ++s_num_pud_reqs[*legacy_pud_statistic_slot(req.type_id)];
    return true;
  }
  bool reserve(int source, int engine) {
    auto [buffer, it] = find(source);
    return reserve_pud_compute(*it, engine);
  }
  bool available(const Request& req, int engine) const {
    return pud_compute_resources_available(req, engine);
  }
  void dispatch(int source, Clk_t clk, bool coincident_terminal) {
    advance(clk);
    auto [buffer, it] = find(source);
    auto& context = protected_pud_context(*it);
    const auto occurrence = describe_pud_occurrence(*it, it->occurrence_index, *m_device.m_spec);
    // A synthetic completion-queue tie fixture may give two terminal PREs the
    // same clock. This tests simultaneous recovery release, not C/A scheduling.
    if (clk <= last_issue && !(coincident_terminal && occurrence.terminal && clk == last_issue)) {
      throw std::logic_error("fixture C/A slot occupied");
    }
    it->command = occurrence.command;
    m_device.issue_pud_command(*it, occurrence, &context, m_clk);
    last_issue = clk;
    if (occurrence.terminal) retire_request(it, *buffer);
    else if (buffer != &m_active_buffer) promote_to_active(it, *buffer);
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
  bool saved_expired(size_t id) const { return saved.at(id).pud_compute_context.expired(); }
  bool reserve_saved(size_t id, int engine) { return reserve_pud_compute(saved.at(id), engine); }
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
    out["rw_buffered"] = m_read_buffer.size() + m_write_buffer.size();
    nb::list held;
    for (const auto& record : m_protected_compute) {
      nb::dict item;
      item["engine"] = record.engine;
      item["phase"] = static_cast<int>(record.context->phase());
      item["recovery"] = record.context->recovery_ready_clk();
      item["completion_pending"] = record.completion_pending;
      item["rows"] = record.context->activated_operands();
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
// public ingress and arbitration; no target transport or allocation policy.
namespace Ramulator {
class PuDConflictUnderTest {
 public:
  explicit PuDConflictUnderTest(nb::dict config) : dut(config, 8), ctrl(dut.m_controller_base) {}
  bool add(Request req, int source, int engine) {
    initialize_pud_sequence(req, *ctrl->m_device.m_spec);
    req.source_id = source;
    req.arrive = ctrl->m_clk;
    if (!ctrl->reserve_pud_compute(req, engine)) return false;
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
    if (last_issue == clk) throw std::logic_error("fixture shared issue slot occupied");
    auto& req = compute.at(source);
    if (!ctrl->is_pud_eligible_before_prerequisite(req)) throw std::logic_error("fixture compute blocked");
    const auto occ = describe_pud_occurrence(req, req.occurrence_index, *ctrl->m_device.m_spec);
    req.command = occ.command;
    ctrl->m_device.issue_pud_command(req, occ, &ctrl->protected_pud_context(req), clk);
    last_issue = clk;
    if (occ.terminal) {
      ReqBuffer retiring;
      retiring.enqueue(req);
      auto it = retiring.begin();
      ctrl->retire_request(it, retiring);
    }
  }
  void advance(Clk_t clk) {
    if (clk < ctrl->m_clk) throw std::logic_error("fixture clock cannot go backwards");
    while (ctrl->m_clk < clk) {
      for (auto event : dut.tick()) {
        history.append(event);
        last_issue = ctrl->m_clk;
      }
    }
  }
  void movement(Request req, int source) {
    validate_pud_placement(req, *ctrl->m_device.m_spec, 0,
                           get_pud_placement_levels(*ctrl->m_device.m_spec));
    // Explicit legacy fixture conversion; this is not a v2 dispatch path. The
    // separate located lifetime fixture checks the paired endpoint retention.
    const auto& source_mats = req.pud_locations->operands[0].location.origin.mats;
    const auto& destination_mats = req.pud_locations->operands[1].location.origin.mats;
    if (req.type_id == Request::Type::LCMOV) {
      req.movement = Request::LCMovementMetadata{{source_mats.first, source_mats.last}};
    } else {
      req.movement = Request::GBMovementMetadata{source_mats.first, destination_mats.first};
    }
    req.pud_locations.reset();
    req.source_id = source;
    req.callback = [this](Request& r) {
      nb::dict event = movement_snapshot(r);
      event["source"] = r.source_id;
      event["depart"] = r.depart;
      completed.append(event);
    };
    if (!ctrl->send(req)) throw std::logic_error("fixture movement enqueue failed");
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
  void send(int type, const AddrVec_t& addr, int source) { dut.send_request(type, addr, source); }
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
  size_t held() const { return ctrl->m_protected_compute.size(); }
  nb::dict stats() { ctrl->update_stats(); return nb::cast<nb::dict>(confignode_to_py(ctrl->IController::collect_stats())); }
  void capacity(size_t active) { ctrl->m_active_buffer.max_size = active; }

 private:
  static nb::dict movement_snapshot(const Request& req) {
    auto out = located_snapshot(req, false);
    auto state = describe_pud_movement_state(req);
    out["source_active"] = state.source_active;
    out["destination_active"] = state.destination_active;
    out["source_valid"] = state.source_valid;
    out["owns_bank"] = state.owns_bank;
    return out;
  }
  ControllerUnderTestCpp dut;
  ControllerBase* ctrl;
  std::map<int, Request> compute;
  nb::list history;
  nb::list completed;
  Clk_t last_issue = -1;
};

}  // namespace Ramulator

inline void bind_pud_request_harness(nb::module_& m) {
  nb::class_<PuDConflictUnderTest>(m, "_PuDConflictUnderTest")
      .def(nb::init<nb::dict>())
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
      .def("capacity", &PuDConflictUnderTest::capacity);
  nb::class_<ComputeLifecycleUnderTest>(m, "_ComputeLifecycleUnderTest")
      .def(nb::init<nb::dict>())
      .def("add", &ComputeLifecycleUnderTest::add, nb::arg("req"), nb::arg("source"),
           nb::arg("callback") = nb::none())
      .def("reserve", &ComputeLifecycleUnderTest::reserve)
      .def("available", &ComputeLifecycleUnderTest::available)
      .def("dispatch", &ComputeLifecycleUnderTest::dispatch, nb::arg("source"), nb::arg("clk"),
           nb::arg("coincident_terminal") = false)
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
      .def("corrupt_descriptor", &ComputeRangesUnderTest::corrupt_descriptor)
      .def("dispatch", &ComputeRangesUnderTest::dispatch, nb::arg("id"), nb::arg("clk"),
           nb::arg("issue") = false, nb::arg("context_id") = -1, nb::arg("descriptor") = -1,
           nb::arg("command") = "", nb::arg("stale_request") = false, nb::arg("foreign_device") = false)
      .def("state", &ComputeRangesUnderTest::state, nb::arg("id"), nb::arg("clk") = 0)
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
    Request req(std::move(operands), type);
    req.size_bytes = size;
    return req;
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
      .def("ordinary", &LocatedSystemUnderTest::ordinary, nb::arg("address"), nb::arg("type"), nb::arg("size") = 1,
           nb::arg("cells") = true, nb::arg("wrong_intra") = nb::none())
      .def("stats", &LocatedSystemUnderTest::stats)
      .def("forwarding", &LocatedSystemUnderTest::forwarding)
      .def_prop_ro("pending", &LocatedSystemUnderTest::pending);
}

#endif
