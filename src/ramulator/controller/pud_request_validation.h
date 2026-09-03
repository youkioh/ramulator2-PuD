#ifndef RAMULATOR_CONTROLLER_PUD_REQUEST_VALIDATION_H
#define RAMULATOR_CONTROLLER_PUD_REQUEST_VALIDATION_H

#include <cstdint>

#include "ramulator/base/request.h"

namespace Ramulator {

struct DRAMSpec;

struct PuDPlacementLevels {
  int rank = -1;
  int bankgroup = -1;
  int bank = -1;
  int row = -1;
};

PuDPlacementLevels get_pud_placement_levels(const DRAMSpec& spec);

void validate_pud_placement(
    const Request& req, const DRAMSpec& spec, int controller_channel_id,
    const PuDPlacementLevels& levels);

std::uint64_t get_movement_moved_bits(
    const Request& req, const DRAMSpec& spec);

}  // namespace Ramulator

#endif  // RAMULATOR_CONTROLLER_PUD_REQUEST_VALIDATION_H
