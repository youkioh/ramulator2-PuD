#include <algorithm>
#include <array>
#include <stdexcept>

#include <fmt/format.h>

#include "ramulator/base/param.h"
#include "ramulator/controller/i_controller.h"
#include "ramulator/memory_system/channel_mapper/i_channel_mapper.h"
#include "ramulator/memory_system/i_memory_system.h"
#include "ramulator/memory_system/pud_request_routing.h"
#include "ramulator/translation/i_translation.h"

namespace Ramulator {

class GenericDRAMSystem final : public IMemorySystem, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IMemorySystem, GenericDRAMSystem, "GenericDRAM");

 protected:
  IChannelMapper* m_channel_mapper;
  std::vector<IController*> m_controllers;
  unsigned int m_clock_ratio = 1;
  int m_tx_bytes = 0;

 public:
  int s_num_read_requests = 0;
  int s_num_write_requests = 0;
  std::array<int, kNumLegacyPuDStatisticSlots> s_num_pud_requests{};
  std::array<int, kNumMovementStatisticSlots> s_num_movement_requests{};

 public:
  void init() override {
    RAMULATOR_PARSE_PARAM(m_clock_ratio, unsigned int, "clock_ratio").required();
    RAMULATOR_CREATE_CHILD(m_channel_mapper, IChannelMapper);

    // Each controller = one channel. DRAM config lives inside each controller.
    RAMULATOR_CREATE_CHILD_LIST(m_controllers, IController);
    if (m_controllers.empty()) {
      throw std::runtime_error("GenericDRAM requires at least one controller");
    }
    for (size_t i = 0; i < m_controllers.size(); i++) {
      dynamic_cast<Implementation*>(m_controllers[i])->set_id(fmt::format("Channel {}", i));
      m_controllers[i]->set_channel_id(static_cast<int>(i));
      m_controllers[i]->m_clock_ratio = m_clock_ratio;
    }

    // Setup channel mapper with controller info
    m_tx_bytes = m_controllers[0]->get_tx_bytes();
    m_channel_mapper->setup(static_cast<int>(m_controllers.size()), calc_log2(m_tx_bytes));

    m_stats.add("total_num_read_requests", s_num_read_requests);
    m_stats.add("total_num_write_requests", s_num_write_requests);
    for (int type_id = 0; type_id < Request::Type::Count; type_id++) {
      const auto slot = legacy_pud_statistic_slot(type_id);
      if (slot.has_value()) {
        m_stats.add(
            fmt::format("total_num_pud_{}_requests", legacy_pud_statistic_name(type_id)),
            s_num_pud_requests[*slot]);
      }
    }
    const bool supports_movement = std::all_of(
        m_controllers.begin(), m_controllers.end(),
        [](const IController* controller) {
          return controller->supports_movement_requests();
        });
    if (supports_movement) {
      for (int type_id : {Request::Type::LCMOV, Request::Type::GBMOV}) {
        const auto slot = movement_statistic_slot(type_id);
        m_stats.add(
            fmt::format("total_num_pud_{}_requests", movement_statistic_name(type_id)),
            s_num_movement_requests[*slot]);
      }
    }
  };

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
  }

  bool send(Request& req) override {
    if (!is_valid_external_request_size(req.type_id, req.size_bytes, m_tx_bytes)) {
      if (is_movement_request_type(req.type_id)) {
        throw std::runtime_error(fmt::format(
            "{} request size_bytes must use the N/A sentinel {} (got {}).",
            request_type_name(req.type_id), Request::kMovementSizeBytesNotApplicable,
            req.size_bytes));
      }
      throw std::runtime_error(fmt::format(
          "Request size_bytes must be set by the frontend (got {}, tx_bytes = {}).",
          req.size_bytes, m_tx_bytes));
    }

    int channel_id = -1;
    if (is_pud_request_type(req.type_id)) {
      channel_id = validate_pud_routing(req, static_cast<int>(m_controllers.size()));
    } else {
      // Channel mapper sets req.addr_vec[0] and req.intra_channel_addr.
      // Controller::send() handles address mapping internally.
      m_channel_mapper->apply(req);
      channel_id = req.addr_vec[0];
    }
    bool is_success = m_controllers[channel_id]->send(req);

    if (is_success) {
      switch (req.type_id) {
        case Request::Type::Read: {
          s_num_read_requests++;
          break;
        }
        case Request::Type::Write: {
          s_num_write_requests++;
          break;
        }
        default:
          if (const auto slot = legacy_pud_statistic_slot(req.type_id); slot.has_value()) {
            s_num_pud_requests[*slot]++;
          } else if (const auto slot = movement_statistic_slot(req.type_id);
                     slot.has_value()) {
            s_num_movement_requests[*slot]++;
          }
          break;
      }
    }
    return is_success;
  };

  void tick() override {
    for (auto controller : m_controllers) {
      controller->tick();
    }
  };

  void reset_stats() override {
    s_num_read_requests = 0;
    s_num_write_requests = 0;
    s_num_pud_requests.fill(0);
    s_num_movement_requests.fill(0);
  }

  int get_clock_ratio() override {
    return m_clock_ratio;
  }

  float get_tCK() override {
    if (!m_controllers.empty()) {
      return m_controllers[0]->get_tCK();
    }
    return -1.0f;
  }

  int get_tx_bytes() override {
    return m_tx_bytes;
  }
};

}  // namespace Ramulator
