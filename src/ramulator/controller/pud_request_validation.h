#ifndef RAMULATOR_CONTROLLER_PUD_REQUEST_VALIDATION_H
#define RAMULATOR_CONTROLLER_PUD_REQUEST_VALIDATION_H

#include <cstdint>

#include "ramulator/base/request.h"

namespace Ramulator {

struct DRAMSpec;

struct PuDPlacementLevels {
  std::vector<int> bank_context;
  int row = -1;
};

PuDPlacementLevels get_pud_placement_levels(const DRAMSpec& spec);

void validate_pud_placement(
    const Request& req, const DRAMSpec& spec, int controller_channel_id,
    const PuDPlacementLevels& levels, const PuD::LocationResolver* resolver = nullptr);

// On-demand ordinary consumer result; size annotates the requested byte region,
// while ACT and RD/WR always describe their complete canonical footprints.
struct OrdinaryRequestLocations {
  PuD::ResolvedBit origin;
  int requested_size_bytes;
  PuD::ResolvedRegion activation;
  PuD::ResolvedRegion burst;
};
OrdinaryRequestLocations resolve_ordinary_request(
    const Request& req, const PuD::LocationResolver& resolver);

std::uint64_t get_movement_moved_bits(
    const Request& req, const DRAMSpec& spec);

}  // namespace Ramulator

#endif  // RAMULATOR_CONTROLLER_PUD_REQUEST_VALIDATION_H
