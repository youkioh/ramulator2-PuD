#ifndef RAMULATOR_MEMORY_SYSTEM_PUD_REQUEST_ROUTING_H
#define RAMULATOR_MEMORY_SYSTEM_PUD_REQUEST_ROUTING_H

#include <stdexcept>

#include <fmt/format.h>

#include "ramulator/base/request.h"

namespace Ramulator {

inline void validate_pud_operand_count(const Request& req) {
  const size_t count = req.operands.size();
  bool valid = false;
  switch (req.type_id) {
    case Request::Type::RowCopy: valid = count >= 2; break;
    case Request::Type::MAJ3: valid = count == 3; break;
    case Request::Type::MAJ5: valid = count == 5; break;
    case Request::Type::NOT: valid = count == 1; break;
    default:
      throw std::runtime_error(fmt::format("Invalid PuD request type_id {}", req.type_id));
  }
  if (!valid) {
    throw std::runtime_error(fmt::format(
        "{} request has invalid operand count {}", request_type_name(req.type_id), count));
  }
}

inline int validate_pud_routing(const Request& req, int num_channels) {
  validate_pud_operand_count(req);

  int route_channel = -1;
  for (size_t i = 0; i < req.operands.size(); i++) {
    const auto& operand = req.operands[i];
    if (operand.empty()) {
      throw std::runtime_error(fmt::format(
          "{} operand {} has no channel coordinate", request_type_name(req.type_id), i));
    }
    int channel = operand[0];
    if (channel < 0 || channel >= num_channels) {
      throw std::runtime_error(fmt::format(
          "{} operand {} has channel {} outside [0, {})",
          request_type_name(req.type_id), i, channel, num_channels));
    }
    if (i == 0) {
      route_channel = channel;
    } else if (channel != route_channel) {
      throw std::runtime_error(fmt::format(
          "{} operands must share a channel: operand 0 targets {}, operand {} targets {}",
          request_type_name(req.type_id), route_channel, i, channel));
    }
  }
  return route_channel;
}

}  // namespace Ramulator

#endif  // RAMULATOR_MEMORY_SYSTEM_PUD_REQUEST_ROUTING_H
