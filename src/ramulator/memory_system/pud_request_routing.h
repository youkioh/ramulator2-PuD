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
    case Request::Type::NOT_COPY: valid = count == 2; break;
    case Request::Type::LCMOV:
    case Request::Type::GBMOV: valid = count == 2; break;
    default:
      throw std::runtime_error(fmt::format("Invalid PuD request type_id {}", req.type_id));
  }
  if (!valid) {
    throw std::runtime_error(fmt::format(
        "{} request has invalid operand count {}", request_type_name(req.type_id), count));
  }
}

inline void validate_movement_metadata(const Request& req) {
  if (req.pud_locations) {
    if (!std::holds_alternative<std::monostate>(req.movement)) {
      throw std::runtime_error("PuD scope must come from paired operands, not separate movement metadata");
    }
    return;
  }
  bool valid = false;
  switch (req.type_id) {
    case Request::Type::LCMOV:
      valid = std::holds_alternative<Request::LCMovementMetadata>(req.movement);
      break;
    case Request::Type::GBMOV:
      valid = std::holds_alternative<Request::GBMovementMetadata>(req.movement);
      break;
    default: return;
  }
  if (!valid) {
    throw std::runtime_error(fmt::format(
        "{} request is missing its required typed movement metadata",
        request_type_name(req.type_id)));
  }
}

inline void validate_pud_pairs(const Request& req, const PuD::LocationResolver* expected = nullptr) {
  if (!req.pud_locations || !req.pud_locations->resolver) {
    throw std::runtime_error("PuD requires resolver-produced paired operands and origins");
  }
  const auto& locations = *req.pud_locations;
  if (expected && &expected->association() != &locations.resolver->association()) {
    throw std::runtime_error("PuD profile/routing association does not match the controller");
  }
  if (locations.operands.size() != req.operands.size()) {
    throw std::runtime_error("PuD paired operand count mismatch");
  }
  for (size_t i = 0; i < locations.operands.size(); ++i) {
    locations.resolver->validate(locations.operands[i]);
    if (req.operands[i] != locations.operands[i].external) {
      throw std::runtime_error("PuD external projection was changed independently");
    }
  }
}

inline int validate_pud_routing(const Request& req, int num_channels) {
  validate_pud_operand_count(req);
  if (!req.pud_locations) {
    throw std::runtime_error("PuD requires canonical resolved locations");
  }
  if (req.pud_locations) {
    validate_pud_pairs(req);
  }
  validate_movement_metadata(req);

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
