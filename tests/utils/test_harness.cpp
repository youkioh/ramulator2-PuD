#include <nanobind/nanobind.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include <fmt/format.h>
#include <memory>
#include <stdexcept>
#include <string>

#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/pud_request_validation.h"
#include "ramulator/controller/i_controller.h"
#include "ramulator/controller/plugin/controller_validation_hook.h"
#include "ramulator/dram/device.h"
#include "ramulator/dram/dram_spec.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/channel_mapper/i_channel_mapper.h"
#include "ramulator/memory_system/i_memory_system.h"
#include "ramulator/memory_system/pud_request_routing.h"
#include "ramulator/python/binding_utils.h"

// ---- DeviceUnderTest ----

class DeviceUnderTestCpp {
 public:
  explicit DeviceUnderTestCpp(nb::dict dram_config, int channel_id) {
    ConfigNode cfg = py_to_confignode(dram_config);
    std::string dram_impl = cfg["impl"].as<std::string>();
    m_device.init(DRAMSpec::create(dram_impl, ConfigNode(ConfigNode::Map{{"dram", std::move(cfg)}})));
    m_device.set_channel_id(channel_id);
  }

  std::vector<std::string> level_names() const {
    return spec().level_names;
  }

  std::vector<std::string> command_names() const {
    return spec().command_names;
  }

  std::vector<std::string> state_names() const {
    return spec().state_names;
  }

  nb::dict command_info(const std::string& command_name) const {
    int command = spec().get_command_id(command_name);
    const auto& meta = spec().command_meta[command];

    nb::dict out;
    out["is_opening"] = meta.is_opening;
    out["is_closing"] = meta.is_closing;
    out["is_accessing"] = meta.is_accessing;
    out["is_refreshing"] = meta.is_refreshing;
    switch (spec().bank_targets[command]) {
      case BankTarget::Single:
        out["bank_target"] = "Single";
        break;
      case BankTarget::All:
        out["bank_target"] = "All";
        break;
      case BankTarget::SameBank:
        out["bank_target"] = "SameBank";
        break;
    }
    out["has_action"] = spec().funcs.actions[command] != nullptr;
    out["has_preq"] = spec().funcs.preqs[command] != nullptr;
    out["has_rowhit"] = spec().funcs.rowhits[command] != nullptr;
    out["has_rowopen"] = spec().funcs.rowopens[command] != nullptr;
    return out;
  }

  std::map<std::string, int> timings() const {
    return timing_map(spec());
  }

  int timing(const std::string& name) const {
    return spec().get_timing_value(name);
  }

  bool supports_controller_sequenced_request(int type_id) const {
    return spec().supports_controller_sequenced_request(type_id);
  }

  bool supports_inherited_pud_requests() const {
    return spec().supports_inherited_pud_requests();
  }

  bool supports_movement_requests() const {
    return spec().supports_movement_requests();
  }

  bool supports_hffs_per_mat_config() const {
    return spec().supports_hffs_per_mat;
  }

  int hffs_per_mat() const {
    return spec().hffs_per_mat.value_or(-1);
  }

  nb::dict bank_info(const AddrVec_t& addr_vec) const {
    validate_addr_vec_size(spec(), addr_vec);
    int bank_id = m_device.get_flat_bank_id(addr_vec);
    if (bank_id < 0 || bank_id >= static_cast<int>(m_device.m_bank_nodes.size())) {
      throw std::runtime_error("bank_info address does not identify a valid Bank");
    }

    const auto* bank = m_device.m_bank_nodes[bank_id];
    std::map<int, std::string> row_state;
    for (const auto& [row, state] : bank->m_row_state) {
      row_state[row] = spec().state_names[state];
    }

    nb::dict out;
    out["state"] = spec().state_names[bank->m_state];
    out["row_state"] = row_state;
    return out;
  }

  nb::dict probe(const std::string& command_name, const AddrVec_t& addr_vec, Clk_t clk) {
    validate_addr_vec_size(spec(), addr_vec);
    int cmd = spec().get_command_id(command_name);

    int preq = m_device.get_preq_command(cmd, addr_vec, clk);
    bool timing_ok = m_device.check_timing(cmd, addr_vec, clk);
    bool ready = (preq == cmd) && timing_ok;

    bool row_hit = false;
    bool row_open = false;
    if (can_query_bank_local_state(cmd, addr_vec)) {
      row_hit = m_device.check_rowbuffer_hit(cmd, addr_vec, clk);
      row_open = m_device.check_node_open(cmd, addr_vec, clk);
    }

    nb::dict out;
    out["preq"] = spec().command_names[preq];
    out["timing_OK"] = timing_ok;
    out["ready"] = ready;
    out["row_hit"] = row_hit;
    out["row_open"] = row_open;
    return out;
  }

  void issue(const std::string& command_name, const AddrVec_t& addr_vec, Clk_t clk) {
    validate_addr_vec_size(spec(), addr_vec);
    int cmd = spec().get_command_id(command_name);

    int preq = m_device.get_preq_command(cmd, addr_vec, clk);
    if (preq != cmd) {
      throw std::runtime_error("Cannot issue command '" + command_name + "' at clk=" + std::to_string(clk) +
                               ": prerequisite is '" + spec().command_names[preq] + "'");
    }

    if (!m_device.check_timing(cmd, addr_vec, clk)) {
      throw std::runtime_error("Cannot issue command '" + command_name + "' at clk=" + std::to_string(clk) +
                               ": timing not ready");
    }

    m_device.issue_command(cmd, addr_vec, clk);
  }

 private:
  DRAMDevice m_device;

  const DRAMSpec& spec() const {
    return *m_device.m_spec;
  }

  bool can_query_bank_local_state(int command, const AddrVec_t& addr_vec) const {
    if (!spec().has_level("Bank") || spec().bank_targets[command] != BankTarget::Single) {
      return false;
    }
    int bank_level = spec().get_level_id("Bank");
    for (int lvl = 0; lvl <= bank_level; lvl++) {
      if (addr_vec[lvl] < 0) {
        return false;
      }
    }
    return true;
  }
};

// ---- ControllerUnderTest harness ----

class HarnessFrontEnd final : public IFrontEnd, public Implementation {
 public:
  explicit HarnessFrontEnd(int num_cores)
      : Implementation(ConfigNode(ConfigNode::Map{}), IFrontEnd::get_name(), "HarnessFrontEnd", nullptr),
        m_num_cores(num_cores) {
    IFrontEnd::m_impl = this;
  }

  void init() override {}
  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {}
  void tick() override {}
  bool is_finished() override { return false; }
  int get_num_cores() override { return m_num_cores; }

 protected:
  std::string get_name() const override { return "HarnessFrontEnd"; }
  std::string get_ifce_name() const override { return IFrontEnd::get_name(); }

 private:
  int m_num_cores = 1;
};

class HarnessMemorySystem final : public IMemorySystem, public Implementation {
 public:
  explicit HarnessMemorySystem(ConfigNode controller_config)
      : Implementation(ConfigNode(ConfigNode::Map{}), IMemorySystem::get_name(), "HarnessMemorySystem", nullptr) {
    IMemorySystem::m_impl = this;

    ConfigNode wrapped = wrap_interface_config(IController::get_name(), std::move(controller_config));
    Implementation* controller_impl = Factory::create_implementation(IController::get_name(), wrapped, this);
    add_child(controller_impl);

    m_controller = dynamic_cast<IController*>(controller_impl);
    if (!m_controller) {
      throw std::runtime_error("HarnessMemorySystem failed to create a controller");
    }
    controller_impl->set_id("Channel 0");
    m_controller->m_channel_id = 0;
    m_controller->m_clock_ratio = 1;

    gather_components();
  }

  void init() override {}
  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {}

  bool send(Request& req) override {
    if (is_pud_request_type(req.type_id)) {
      int channel = validate_pud_routing(req, 1);
      if (channel != 0) {
        throw std::runtime_error("HarnessMemorySystem only owns channel 0");
      }
      return m_controller->send(req);
    }
    if (req.intra_channel_addr < 0) {
      req.intra_channel_addr = req.addr;
    }
    return m_controller->send(req);
  }

  void tick() override {
    m_controller->tick();
  }

  int get_clock_ratio() override { return m_controller->m_clock_ratio; }
  float get_tCK() override { return m_controller->get_tCK(); }
  int get_tx_bytes() override { return m_controller->get_tx_bytes(); }

  IController* controller() const { return m_controller; }

  template <typename T>
  T* find_component() const {
    for (auto* component : m_components) {
      if (auto* typed = dynamic_cast<T*>(component)) {
        return typed;
      }
    }
    return nullptr;
  }

 protected:
  std::string get_name() const override { return "HarnessMemorySystem"; }
  std::string get_ifce_name() const override { return IMemorySystem::get_name(); }

 private:
  IController* m_controller = nullptr;
};

// Test-only controller used to observe which GenericDRAMSystem channel receives
// a request without exposing the production controller list.
class RoutingControllerStub final : public IController, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IController, RoutingControllerStub, "RoutingControllerStub");

 public:
  inline static int last_receiver = -1;
  inline static Request last_request{};
  inline static bool reject_next = false;

  static void reset(bool reject_first = false) {
    last_receiver = -1;
    last_request = Request{};
    reject_next = reject_first;
  }

  void init() override {}
  bool send(Request& req) override {
    if (reject_next) {
      reject_next = false;
      return false;
    }
    last_receiver = m_channel_id;
    last_request = req;
    return true;
  }
  bool priority_send(Request& req) override { return send(req); }
  void tick() override {}
  int get_tx_bytes() const override { return 64; }
  int get_num_levels() const override { return 0; }
  float get_tCK() const override { return 1.0f; }
};

class PuDRoutingSystemUnderTestCpp {
 public:
  explicit PuDRoutingSystemUnderTestCpp(int num_channels)
      : m_frontend(std::make_unique<HarnessFrontEnd>(1)) {
    if (num_channels <= 0) {
      throw std::runtime_error("PuDRoutingSystemUnderTest requires at least one channel");
    }

    ConfigNode::Seq controllers;
    for (int channel = 0; channel < num_channels; channel++) {
      controllers.emplace_back(ConfigNode::Map{{"impl", "RoutingControllerStub"}});
    }
    ConfigNode system_config(ConfigNode::Map{
        {"impl", "GenericDRAM"},
        {"clock_ratio", 1},
        {"channel_mapper", ConfigNode::Map{{"impl", "PassThroughChannelMapper"}}},
        {"controllers", std::move(controllers)},
    });
    ConfigNode wrapped = wrap_interface_config(IMemorySystem::get_name(), std::move(system_config));
    m_memory_system = Factory::create_memory_system(wrapped);
    m_memory_system_impl.reset(dynamic_cast<Implementation*>(m_memory_system));
    if (!m_memory_system_impl) {
      throw std::runtime_error("PuDRoutingSystemUnderTest failed to create GenericDRAMSystem");
    }

    m_frontend->connect_memory_system(m_memory_system);
    m_memory_system->connect_frontend(m_frontend.get());
  }

  nb::dict send_pud_request(
      int type_id, const std::vector<AddrVec_t>& operands, int size_bytes = 64) {
    RoutingControllerStub::reset();
    Request req(operands, type_id);
    req.size_bytes = size_bytes;
    if (!m_memory_system->send(req)) {
      throw std::runtime_error("GenericDRAMSystem failed to route PuD request");
    }

    nb::dict out;
    out["receiver"] = RoutingControllerStub::last_receiver;
    out["operands"] = RoutingControllerStub::last_request.operands;
    return out;
  }

  nb::dict send_regular_request(int type_id, const AddrVec_t& addr_vec, int size_bytes) {
    RoutingControllerStub::reset();
    Request req(addr_vec, type_id);
    req.addr = 0;
    req.size_bytes = size_bytes;
    if (!m_memory_system->send(req)) {
      throw std::runtime_error("GenericDRAMSystem failed to route regular request");
    }

    nb::dict out;
    out["receiver"] = RoutingControllerStub::last_receiver;
    out["size_bytes"] = RoutingControllerStub::last_request.size_bytes;
    return out;
  }

  nb::dict send_movement_request(
      int type_id,
      const std::vector<AddrVec_t>& operands,
      const std::string& metadata_kind,
      int first_mat,
      int second_mat,
      int size_bytes = Request::kMovementSizeBytesNotApplicable,
      bool retry_once = false) {
    RoutingControllerStub::reset(retry_once);
    Request req(operands, type_id);
    req.size_bytes = size_bytes;
    if (metadata_kind == "LC") {
      req.movement = Request::LCMovementMetadata{{first_mat, second_mat}};
    } else if (metadata_kind == "GB") {
      req.movement = Request::GBMovementMetadata{first_mat, second_mat};
    } else if (!metadata_kind.empty()) {
      throw std::runtime_error("Unknown movement metadata kind " + metadata_kind);
    }

    bool accepted = m_memory_system->send(req);
    if (!accepted && retry_once) {
      accepted = m_memory_system->send(req);
    }
    if (!accepted) {
      throw std::runtime_error("GenericDRAMSystem failed to route movement request");
    }

    const Request& stored = RoutingControllerStub::last_request;
    nb::dict out;
    out["receiver"] = RoutingControllerStub::last_receiver;
    out["operands"] = stored.operands;
    out["size_bytes"] = stored.size_bytes;
    if (const auto* lc = std::get_if<Request::LCMovementMetadata>(&stored.movement)) {
      out["metadata_kind"] = "LC";
      out["first_mat"] = lc->mats.begin;
      out["second_mat"] = lc->mats.end;
    } else if (const auto* gb = std::get_if<Request::GBMovementMetadata>(&stored.movement)) {
      out["metadata_kind"] = "GB";
      out["first_mat"] = gb->source_mat;
      out["second_mat"] = gb->destination_mat;
    } else {
      out["metadata_kind"] = "";
      out["first_mat"] = -1;
      out["second_mat"] = -1;
    }
    return out;
  }

  nb::dict stats() const {
    return nb::cast<nb::dict>(confignode_to_py(m_memory_system_impl->collect_stats()));
  }

 private:
  std::unique_ptr<HarnessFrontEnd> m_frontend;
  std::unique_ptr<Implementation> m_memory_system_impl;
  IMemorySystem* m_memory_system = nullptr;
};

// ---- ChannelMapperUnderTest harness ----

class ChannelMapperUnderTestCpp {
 public:
  ChannelMapperUnderTestCpp(nb::dict mapper_config, int num_channels, int tx_offset) {
    ConfigNode cfg = py_to_confignode(mapper_config);
    ConfigNode wrapped = wrap_interface_config(IChannelMapper::get_name(), std::move(cfg));
    Implementation* mapper_impl =
        Factory::create_implementation(IChannelMapper::get_name(), wrapped, nullptr);
    m_impl.reset(mapper_impl);

    m_mapper = dynamic_cast<IChannelMapper*>(mapper_impl);
    if (!m_mapper) {
      throw std::runtime_error("ChannelMapperUnderTest failed to create a channel mapper");
    }

    m_mapper->setup(num_channels, tx_offset);
  }

  nb::dict apply(Addr_t addr, int ingress_id, int source_id) const {
    Request req(addr, Request::Type::Read);
    req.source_id = source_id;
    req.ingress_id = ingress_id;

    m_mapper->apply(req);

    nb::dict out;
    out["addr"] = req.addr;
    out["intra_channel_addr"] = req.intra_channel_addr;
    out["addr_vec"] = req.addr_vec;
    out["channel"] = req.addr_vec.empty() ? -1 : req.addr_vec[0];
    return out;
  }

 private:
  std::unique_ptr<Implementation> m_impl;
  IChannelMapper* m_mapper = nullptr;
};

class ControllerUnderTestCpp {
 public:
  inline static constexpr int kHarnessInternalSourceId = -2;

  ControllerUnderTestCpp(nb::dict controller_config, int num_cores)
      : m_frontend(std::make_unique<HarnessFrontEnd>(num_cores)),
        m_memory_system(std::make_unique<HarnessMemorySystem>(
            inject_issued_command_validation_hook(py_to_confignode(controller_config)))) {
    m_frontend->connect_memory_system(m_memory_system.get());
    m_memory_system->connect_frontend(m_frontend.get());

    m_controller = m_memory_system->controller();
    m_controller_base = dynamic_cast<ControllerBase*>(m_controller);
    if (!m_controller_base) {
      throw std::runtime_error("ControllerUnderTest requires a ControllerBase-derived controller");
    }

    m_validation_hook = m_memory_system->find_component<IControllerValidationHook>();
    if (!m_validation_hook) {
      throw std::runtime_error("ControllerUnderTest could not find IssuedCommandValidationHook");
    }
  }

  std::vector<std::string> level_names() const { return spec().level_names; }
  std::vector<std::string> command_names() const { return spec().command_names; }
  std::map<std::string, int> timings() const { return timing_map(spec()); }

  int timing(const std::string& name) const {
    return spec().get_timing_value(name);
  }

  void send_request(int type_id, const AddrVec_t& addr_vec, int source_id) {
    validate_concrete_addr_vec(addr_vec);
    Request req(addr_vec, type_id);
    req.addr = synthesize_addr(addr_vec);
    req.intra_channel_addr = req.addr;
    req.source_id = source_id;

    bool read_like = is_read_like_request(type_id);
    if (read_like) {
      m_read_completions_pending++;
      req.callback = [this](Request& completed) {
        if (m_read_completions_pending == 0) {
          throw std::runtime_error("ControllerUnderTest read completion accounting underflow");
        }
        m_read_completions_pending--;
        record_completion(completed);
      };
    }

    if (!m_controller->send(req)) {
      if (read_like) {
        m_read_completions_pending--;
      }
      throw std::runtime_error("ControllerUnderTest failed to enqueue request");
    }

    bool was_forwarded = read_like && req.depart != -1;
    if (!was_forwarded) {
      m_command_outstanding++;
    }
  }

  void send_read_with_reentrant_forwarded_read(
      const AddrVec_t& addr_vec,
      int source_id,
      const AddrVec_t& forwarded_addr_vec,
      int forwarded_source_id) {
    validate_concrete_addr_vec(addr_vec);
    validate_concrete_addr_vec(forwarded_addr_vec);

    Request req(addr_vec, Request::Type::Read);
    req.addr = synthesize_addr(addr_vec);
    req.intra_channel_addr = req.addr;
    req.source_id = source_id;
    m_read_completions_pending++;
    req.callback = [this, forwarded_addr_vec, forwarded_source_id](Request& completed) {
      if (m_read_completions_pending == 0) {
        throw std::runtime_error("ControllerUnderTest read completion accounting underflow");
      }
      m_read_completions_pending--;
      record_completion(completed);

      Request forwarded(forwarded_addr_vec, Request::Type::Read);
      forwarded.addr = synthesize_addr(forwarded_addr_vec);
      forwarded.intra_channel_addr = forwarded.addr;
      forwarded.source_id = forwarded_source_id;
      m_read_completions_pending++;
      forwarded.callback = [this](Request& forwarded_completed) {
        if (m_read_completions_pending == 0) {
          throw std::runtime_error("ControllerUnderTest read completion accounting underflow");
        }
        m_read_completions_pending--;
        record_completion(forwarded_completed);
      };

      if (!m_memory_system->send(forwarded)) {
        m_read_completions_pending--;
        throw std::runtime_error("ControllerUnderTest failed to enqueue reentrant forwarded read");
      }
      if (forwarded.depart == -1) {
        throw std::runtime_error("ControllerUnderTest reentrant read was not write-forwarded");
      }
    };

    if (!m_controller->send(req)) {
      m_read_completions_pending--;
      throw std::runtime_error("ControllerUnderTest failed to enqueue reentrant-callback read");
    }
    if (req.depart == -1) {
      m_command_outstanding++;
    }
  }

  nb::dict send_pud_request(int type_id, const std::vector<AddrVec_t>& operands, int source_id) {
    nb::dict out = try_send_pud_request(type_id, operands, source_id);
    if (!nb::cast<bool>(out["accepted"])) {
      throw std::runtime_error("ControllerUnderTest failed to enqueue PuD request");
    }
    return out;
  }

  nb::dict try_send_pud_request(
      int type_id, const std::vector<AddrVec_t>& operands, int source_id) {
    Request req(operands, type_id);
    req.size_bytes = m_controller->get_tx_bytes();
    req.source_id = source_id;
    m_pud_completions_pending++;
    req.callback = [this](Request& completed) {
      if (m_pud_completions_pending == 0) {
        throw std::runtime_error("ControllerUnderTest PuD completion accounting underflow");
      }
      m_pud_completions_pending--;
      record_completion(completed);
    };

    size_t before = m_controller_base->pending_pud_requests().size();
    if (!m_memory_system->send(req)) {
      m_pud_completions_pending--;
      nb::dict out;
      out["accepted"] = false;
      out["type_id"] = req.type_id;
      out["operands"] = req.operands;
      out["addr_vec"] = req.addr_vec;
      out["source_id"] = req.source_id;
      out["arrive"] = req.arrive;
      return out;
    }
    const auto& pending = m_controller_base->pending_pud_requests();
    if (pending.size() != before + 1) {
      throw std::runtime_error("ControllerUnderTest PuD request was not preserved by the controller");
    }
    const Request& stored = pending.buffer.back();
    m_command_outstanding++;

    nb::dict out;
    out["accepted"] = true;
    out["type_id"] = stored.type_id;
    out["operands"] = stored.operands;
    out["addr_vec"] = stored.addr_vec;
    out["source_id"] = stored.source_id;
    out["arrive"] = stored.arrive;
    return out;
  }

  nb::list completions() const {
    nb::list out;
    for (const auto& completed : m_completions) {
      nb::dict item;
      item["type_id"] = completed.type_id;
      item["source_id"] = completed.source_id;
      item["arrive"] = completed.arrive;
      item["depart"] = completed.depart;
      out.append(item);
    }
    return out;
  }

  void priority_send(const std::string& command_name, const AddrVec_t& addr_vec) {
    validate_addr_vec_size(spec(), addr_vec);
    int command = spec().get_command_id(command_name);

    Request req(addr_vec, Request::Cmd, command);
    req.source_id = kHarnessInternalSourceId;
    if (!m_controller->priority_send(req)) {
      throw std::runtime_error("ControllerUnderTest failed to enqueue internal command");
    }
    m_command_outstanding++;
  }

  nb::list tick() {
    m_memory_system->tick();

    nb::list issued;
    for (const auto& rec : m_validation_hook->take_issued_commands_this_tick()) {
      bool pud_final = is_pud_request_type(rec.type_id) &&
                       rec.command == rec.final_command &&
                       spec().command_names[rec.command] == "PREpb";
      bool tracked_final = pud_final ||
                           (!is_pud_request_type(rec.type_id) &&
                            rec.command == rec.final_command &&
                            (rec.type_id != -1 || rec.source_id == kHarnessInternalSourceId));
      if (tracked_final) {
        if (m_command_outstanding == 0) {
          throw std::runtime_error("ControllerUnderTest command accounting underflow");
        }
        m_command_outstanding--;
      }

      nb::dict item;
      item["clk"] = rec.clk;
      item["command"] = spec().command_names[rec.command];
      item["addr_vec"] = rec.addr_vec;
      item["type_id"] = rec.type_id;
      item["source_id"] = rec.source_id;
      issued.append(item);
    }

    return issued;
  }

  bool is_idle() const {
    return m_command_outstanding == 0 &&
           m_read_completions_pending == 0 &&
           m_pud_completions_pending == 0;
  }

  nb::dict stats() {
    if (!m_stats_finalized) {
      m_memory_system->IMemorySystem::finalize();
      m_stats_finalized = true;
    }
    return nb::cast<nb::dict>(confignode_to_py(m_controller->collect_stats()));
  }

 private:
  std::unique_ptr<HarnessFrontEnd> m_frontend;
  std::unique_ptr<HarnessMemorySystem> m_memory_system;
  IController* m_controller = nullptr;
  ControllerBase* m_controller_base = nullptr;
  IControllerValidationHook* m_validation_hook = nullptr;
  size_t m_command_outstanding = 0;
  size_t m_read_completions_pending = 0;
  size_t m_pud_completions_pending = 0;
  bool m_stats_finalized = false;

  struct CompletionRecord {
    int type_id;
    int source_id;
    Clk_t arrive;
    Clk_t depart;
  };
  std::vector<CompletionRecord> m_completions;

  void record_completion(const Request& req) {
    m_completions.push_back({req.type_id, req.source_id, req.arrive, req.depart});
  }

  const DRAMSpec& spec() const {
    return *m_controller_base->m_device.m_spec;
  }

  void validate_concrete_addr_vec(const AddrVec_t& addr_vec) const {
    validate_addr_vec_size(spec(), addr_vec);
    for (int level = 0; level < spec().level_count; level++) {
      if (addr_vec[level] < 0) {
        throw std::runtime_error("ControllerUnderTest.send_request requires a concrete addr_vec");
      }
    }
  }

  bool is_read_like_request(int type_id) const {
    return type_id == Request::Type::Read;
  }

  Addr_t synthesize_addr(const AddrVec_t& addr_vec) const {
    Addr_t addr = 0;
    for (int level = 0; level < spec().level_count; level++) {
      int count = spec().organization.level_sizes[level];
      if (count <= 0) {
        throw std::runtime_error(fmt::format(
            "synthesize_addr: level {} has invalid size {}", level, count));
      }
      addr = addr * count + addr_vec[level];
    }
    return addr;
  }
};

// ---- nanobind module ----

NB_MODULE(_ramulator_test, m) {
  m.doc() = "Ramulator2 test harness bindings";

  nb::class_<DeviceUnderTestCpp>(m, "_DeviceUnderTest")
      .def(nb::init<nb::dict, int>(), nb::arg("dram_config"), nb::arg("channel_id") = 0)
      .def_prop_ro("level_names", &DeviceUnderTestCpp::level_names)
      .def_prop_ro("command_names", &DeviceUnderTestCpp::command_names)
      .def_prop_ro("state_names", &DeviceUnderTestCpp::state_names)
      .def_prop_ro("timings", &DeviceUnderTestCpp::timings)
      .def("timing", &DeviceUnderTestCpp::timing, nb::arg("name"))
      .def("supports_controller_sequenced_request",
           &DeviceUnderTestCpp::supports_controller_sequenced_request,
           nb::arg("type_id"))
      .def("supports_inherited_pud_requests", &DeviceUnderTestCpp::supports_inherited_pud_requests)
      .def("supports_movement_requests", &DeviceUnderTestCpp::supports_movement_requests)
      .def_prop_ro("supports_hffs_per_mat_config", &DeviceUnderTestCpp::supports_hffs_per_mat_config)
      .def_prop_ro("hffs_per_mat", &DeviceUnderTestCpp::hffs_per_mat)
      .def("bank_info", &DeviceUnderTestCpp::bank_info, nb::arg("addr_vec"))
      .def("command_info", &DeviceUnderTestCpp::command_info, nb::arg("command"))
      .def("probe", &DeviceUnderTestCpp::probe, nb::arg("command"), nb::arg("addr_vec"), nb::arg("clk"))
      .def("issue", &DeviceUnderTestCpp::issue, nb::arg("command"), nb::arg("addr_vec"), nb::arg("clk"));

  nb::class_<ChannelMapperUnderTestCpp>(m, "_ChannelMapperUnderTest")
      .def(nb::init<nb::dict, int, int>(),
           nb::arg("mapper_config"),
           nb::arg("num_channels"),
           nb::arg("tx_offset"))
      .def("apply",
           &ChannelMapperUnderTestCpp::apply,
           nb::arg("addr"),
           nb::arg("ingress_id") = -1,
           nb::arg("source_id") = 0);

  nb::class_<ControllerUnderTestCpp>(m, "_ControllerUnderTest")
      .def(nb::init<nb::dict, int>(), nb::arg("controller_config"), nb::arg("num_cores") = 1)
      .def_prop_ro("level_names", &ControllerUnderTestCpp::level_names)
      .def_prop_ro("command_names", &ControllerUnderTestCpp::command_names)
      .def_prop_ro("timings", &ControllerUnderTestCpp::timings)
      .def("timing", &ControllerUnderTestCpp::timing, nb::arg("name"))
      .def("send_request", &ControllerUnderTestCpp::send_request,
           nb::arg("type_id"), nb::arg("addr_vec"), nb::arg("source_id") = 0)
      .def("send_read_with_reentrant_forwarded_read",
           &ControllerUnderTestCpp::send_read_with_reentrant_forwarded_read,
           nb::arg("addr_vec"),
           nb::arg("source_id"),
           nb::arg("forwarded_addr_vec"),
           nb::arg("forwarded_source_id"))
      .def("send_pud_request", &ControllerUnderTestCpp::send_pud_request,
           nb::arg("type_id"), nb::arg("operands"), nb::arg("source_id") = 0)
      .def("try_send_pud_request", &ControllerUnderTestCpp::try_send_pud_request,
           nb::arg("type_id"), nb::arg("operands"), nb::arg("source_id") = 0)
      .def("priority_send", &ControllerUnderTestCpp::priority_send, nb::arg("command"), nb::arg("addr_vec"))
      .def("tick", &ControllerUnderTestCpp::tick)
      .def("is_idle", &ControllerUnderTestCpp::is_idle)
      .def("completions", &ControllerUnderTestCpp::completions)
      .def("stats", &ControllerUnderTestCpp::stats);

  nb::class_<PuDRoutingSystemUnderTestCpp>(m, "_PuDRoutingSystemUnderTest")
      .def(nb::init<int>(), nb::arg("num_channels"))
      .def("send_pud_request", &PuDRoutingSystemUnderTestCpp::send_pud_request,
           nb::arg("type_id"), nb::arg("operands"), nb::arg("size_bytes") = 64)
      .def("send_regular_request", &PuDRoutingSystemUnderTestCpp::send_regular_request,
           nb::arg("type_id"), nb::arg("addr_vec"), nb::arg("size_bytes"))
      .def("send_movement_request", &PuDRoutingSystemUnderTestCpp::send_movement_request,
           nb::arg("type_id"), nb::arg("operands"), nb::arg("metadata_kind"),
           nb::arg("first_mat"), nb::arg("second_mat"),
           nb::arg("size_bytes") = Request::kMovementSizeBytesNotApplicable,
           nb::arg("retry_once") = false)
      .def("stats", &PuDRoutingSystemUnderTestCpp::stats);

  m.def("_validate_pud_routing",
        [](int type_id, const std::vector<AddrVec_t>& operands, int num_channels) {
          Request req(operands, type_id);
          return validate_pud_routing(req, num_channels);
        },
        nb::arg("type_id"), nb::arg("operands"), nb::arg("num_channels"));
  m.def("_request_type_info", [](int type_id) {
    nb::dict out;
    out["name"] = request_type_name(type_id);
    out["inherited_pud"] = is_inherited_pud_request_type(type_id);
    out["movement"] = is_movement_request_type(type_id);
    out["pud"] = is_pud_request_type(type_id);
    out["controller_sequenced"] = is_controller_sequenced_request_type(type_id);
    const auto slot = legacy_pud_statistic_slot(type_id);
    out["legacy_stat_slot"] = slot.has_value() ? nb::cast(*slot) : nb::none();
    return out;
  }, nb::arg("type_id"));
  m.def("_request_size_contract", [](int type_id, int size_bytes, int tx_bytes) {
    return is_valid_external_request_size(type_id, size_bytes, tx_bytes);
  }, nb::arg("type_id"), nb::arg("size_bytes"), nb::arg("tx_bytes"));
  m.def("_internal_request_default_size", []() {
    Request req(AddrVec_t{}, Request::Cmd, 0);
    return req.size_bytes;
  });
  m.def("_validate_movement_placement", [](
      nb::dict dram_config, int type_id, const std::vector<AddrVec_t>& operands,
      const std::string& metadata_kind, int first_mat, int second_mat,
      int controller_channel_id) {
    ConfigNode cfg = py_to_confignode(dram_config);
    std::string dram_impl = cfg["impl"].as<std::string>();
    auto spec = DRAMSpec::create(
        dram_impl, ConfigNode(ConfigNode::Map{{"dram", std::move(cfg)}}));

    Request req(operands, type_id);
    if (metadata_kind == "LC") {
      req.movement = Request::LCMovementMetadata{{first_mat, second_mat}};
    } else if (metadata_kind == "GB") {
      req.movement = Request::GBMovementMetadata{first_mat, second_mat};
    }
    validate_pud_placement(
        req, *spec, controller_channel_id, get_pud_placement_levels(*spec));
    return get_movement_moved_bits(req, *spec);
  }, nb::arg("dram_config"), nb::arg("type_id"), nb::arg("operands"),
     nb::arg("metadata_kind"), nb::arg("first_mat"), nb::arg("second_mat"),
     nb::arg("controller_channel_id") = 0);
}
