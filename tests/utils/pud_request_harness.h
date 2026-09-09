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

inline void bind_pud_request_harness(nb::module_& m) {
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
