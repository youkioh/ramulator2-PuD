#include "ramulator/controller/pud_request_validation.h"

#include <cstdint>
#include <stdexcept>

#include <fmt/format.h>

#include "ramulator/dram/dram_spec.h"
#include "ramulator/memory_system/pud_request_routing.h"

namespace Ramulator {
namespace {

constexpr int kLogicalMatCount = 128;
constexpr int kLogicalMatsPerChip = 16;

void validate_logical_mat(int mat, const char* role, const Request& req) {
  if (mat < 0 || mat >= kLogicalMatCount) {
    throw std::runtime_error(fmt::format(
        "{} {} logical mat {} is outside [0, {})",
        request_type_name(req.type_id), role, mat, kLogicalMatCount));
  }
}

void validate_movement_placement(const Request& req) {
  if (req.operands.size() != 2) {
    throw std::runtime_error(fmt::format(
        "{} request has invalid operand count {} (expected 2)",
        request_type_name(req.type_id), req.operands.size()));
  }

  if (req.type_id == Request::Type::LCMOV) {
    const auto* metadata = std::get_if<Request::LCMovementMetadata>(&req.movement);
    if (metadata == nullptr) {
      throw std::runtime_error("LC-MOV request is missing its required typed movement metadata");
    }
    validate_logical_mat(metadata->mats.begin, "range-begin", req);
    validate_logical_mat(metadata->mats.end, "range-end", req);
    if (metadata->mats.begin > metadata->mats.end) {
      throw std::runtime_error(fmt::format(
          "LC-MOV logical mat range [{}, {}] must be nonempty and ordered",
          metadata->mats.begin, metadata->mats.end));
    }
    return;
  }

  if (req.type_id == Request::Type::GBMOV) {
    const auto* metadata = std::get_if<Request::GBMovementMetadata>(&req.movement);
    if (metadata == nullptr) {
      throw std::runtime_error("GB-MOV request is missing its required typed movement metadata");
    }
    validate_logical_mat(metadata->source_mat, "source", req);
    validate_logical_mat(metadata->destination_mat, "destination", req);

    const int source_chip = metadata->source_mat / kLogicalMatsPerChip;
    const int destination_chip = metadata->destination_mat / kLogicalMatsPerChip;
    if (source_chip != destination_chip) {
      throw std::runtime_error(fmt::format(
          "GB-MOV source and destination logical mats must share a logical chip: {} and {}",
          metadata->source_mat, metadata->destination_mat));
    }

    const int source_local_mat = metadata->source_mat % kLogicalMatsPerChip;
    const int destination_local_mat = metadata->destination_mat % kLogicalMatsPerChip;
    if (destination_local_mat != source_local_mat + 1) {
      throw std::runtime_error(fmt::format(
          "GB-MOV destination local logical mat must be source plus one: {} -> {}",
          source_local_mat, destination_local_mat));
    }
  }
}

void validate_v2_placement(const Request& req, const DRAMSpec& spec, int channel,
                           const PuD::LocationResolver* expected) {
  validate_pud_operand_count(req);
  validate_pud_pairs(req, expected);
  validate_movement_metadata(req);
  const auto& resolver = *req.pud_locations->resolver;
  resolver.validate_spec(spec);
  if (!is_valid_external_request_size(req.type_id, req.size_bytes, spec.get_tx_bytes())) {
    throw std::runtime_error("v2 PuD invalid size_bytes (movement requires N/A)");
  }
  const auto& operands = req.pud_locations->operands;
  const auto& first = operands.front().location.origin;
  for (size_t i = 0; i < operands.size(); ++i) {
    const auto& origin = operands[i].location.origin;
    if (origin.channel != channel) {
      throw std::runtime_error("v2 PuD operand does not target the controller channel");
    }
    if (origin.channel != first.channel || origin.rank != first.rank ||
        origin.bank_group != first.bank_group || origin.bank != first.bank ||
        origin.subarray != first.subarray) {
      throw std::runtime_error("v2 PuD operands must share Bank and subarray context");
    }
    if (is_movement_request_type(req.type_id) != origin.group.has_value()) {
      throw std::runtime_error("v2 PuD requires whole compute mat-rows or explicit movement groups");
    }
    if (req.type_id != Request::Type::GBMOV && origin.mats != first.mats) {
      throw std::runtime_error("v2 PuD operands must share the same mat range");
    }
    if (req.type_id == Request::Type::MAJ3 || req.type_id == Request::Type::MAJ5) {
      for (size_t j = 0; j < i; ++j) {
        if (origin.local_row == operands[j].location.origin.local_row) {
          throw std::runtime_error("v2 majority requires distinct physical rows");
        }
      }
    }
  }
  if (req.type_id == Request::Type::GBMOV) {
    const auto source = first.mats;
    const auto destination = operands[1].location.origin.mats;
    if (source.first != source.last || destination.first != destination.last ||
        resolver.segment_range(source).front().chip != resolver.segment_range(destination).front().chip ||
        !resolver.directed_neighbors(source.first, destination.first)) {
      throw std::runtime_error("v2 GB requires directed singleton neighbors within one chip");
    }
  }
}

}  // namespace

PuDPlacementLevels get_pud_placement_levels(const DRAMSpec& spec) {
  return {
      .rank = spec.get_level_id("Rank"),
      .bankgroup = spec.get_level_id("BankGroup"),
      .bank = spec.get_level_id("Bank"),
      .row = spec.get_level_id("Row"),
  };
}

void validate_pud_placement(
    const Request& req, const DRAMSpec& spec, int controller_channel_id,
    const PuDPlacementLevels& levels, const PuD::LocationResolver* resolver) {
  if (req.pud_locations || resolver) {
    validate_v2_placement(req, spec, controller_channel_id, resolver);
    return;
  }
  if (!spec.geometry.has_subarrays()) {
    throw std::runtime_error(fmt::format(
        "DRAM standard {} does not define PuD subarray geometry", spec.standard_name));
  }
  if (req.operands.empty()) {
    throw std::runtime_error(fmt::format(
        "{} request has no operands", request_type_name(req.type_id)));
  }

  auto validate_operand = [&](const AddrVec_t& operand, size_t operand_idx) {
    if (operand.size() != static_cast<size_t>(spec.level_count)) {
      throw std::runtime_error(fmt::format(
          "{} operand {} has {} hierarchy coordinates; expected {}",
          request_type_name(req.type_id), operand_idx, operand.size(), spec.level_count));
    }
    for (int level = 0; level < spec.level_count; level++) {
      int value = operand[level];
      if (level == 0) {
        if (value != controller_channel_id) {
          throw std::runtime_error(fmt::format(
              "{} operand {} targets channel {}, but controller owns channel {}",
              request_type_name(req.type_id), operand_idx, value, controller_channel_id));
        }
      } else if (value < 0 || value >= spec.organization.level_sizes[level]) {
        throw std::runtime_error(fmt::format(
            "{} operand {} coordinate {} at level {} is outside [0, {})",
            request_type_name(req.type_id), operand_idx, value,
            spec.level_names[level], spec.organization.level_sizes[level]));
      }
    }
  };

  validate_operand(req.operands[0], 0);
  const auto& first = req.operands[0];
  const int first_subarray = spec.geometry.subarray_id(first[levels.row]);

  for (size_t i = 1; i < req.operands.size(); i++) {
    const auto& operand = req.operands[i];
    validate_operand(operand, i);
    for (int level : {levels.rank, levels.bankgroup, levels.bank}) {
      if (operand[level] != first[level]) {
        throw std::runtime_error(fmt::format(
            "{} operands must share {}: operand 0 has {}, operand {} has {}",
            request_type_name(req.type_id), spec.level_names[level],
            first[level], i, operand[level]));
      }
    }
    int subarray = spec.geometry.subarray_id(operand[levels.row]);
    if (subarray != first_subarray) {
      throw std::runtime_error(fmt::format(
          "{} operands must share a logical subarray: operand 0 has {}, operand {} has {}",
          request_type_name(req.type_id), first_subarray, i, subarray));
    }
  }

  if (is_movement_request_type(req.type_id)) {
    validate_movement_placement(req);
  }
}

std::uint64_t get_movement_moved_bits(const Request& req, const DRAMSpec& spec) {
  if (req.pud_locations) {
    if (!is_movement_request_type(req.type_id)) {
      throw std::runtime_error("Cannot derive movement bits for a compute request");
    }
    validate_v2_placement(req, spec, req.operands.at(0).at(0), nullptr);
    return static_cast<std::uint64_t>(req.pud_locations->operands.front().location.cell_count);
  }
  if (!spec.hffs_per_mat.has_value() || *spec.hffs_per_mat <= 0) {
    throw std::runtime_error(fmt::format(
        "DRAM standard {} does not define a positive hffs_per_mat",
        spec.standard_name));
  }

  const auto hffs_per_mat = static_cast<std::uint64_t>(*spec.hffs_per_mat);
  if (req.type_id == Request::Type::LCMOV) {
    const auto* metadata = std::get_if<Request::LCMovementMetadata>(&req.movement);
    if (metadata == nullptr || metadata->mats.begin < 0 ||
        metadata->mats.end < metadata->mats.begin ||
        metadata->mats.end >= kLogicalMatCount) {
      throw std::runtime_error("LC-MOV moved bits require validated movement metadata");
    }
    const auto selected_mat_count =
        static_cast<std::uint64_t>(metadata->mats.end - metadata->mats.begin + 1);
    return selected_mat_count * hffs_per_mat;
  }
  if (req.type_id == Request::Type::GBMOV &&
      std::holds_alternative<Request::GBMovementMetadata>(req.movement)) {
    return hffs_per_mat;
  }
  throw std::runtime_error(fmt::format(
      "Cannot derive movement bits for request type {}", req.type_id));
}

OrdinaryRequestLocations resolve_ordinary_request(const Request& req, const PuD::LocationResolver& resolver) {
  if ((req.type_id != Request::Type::Read && req.type_id != Request::Type::Write) || req.pud_locations) {
    throw std::runtime_error("ordinary location resolution requires Read or Write");
  }
  auto origin = resolver.resolve(PuD::PhysicalBit{req.addr, 0});
  if (req.addr_vec != origin.external.addr_vec()) {
    throw std::runtime_error("ordinary mapper result disagrees with canonical projection");
  }
  return {origin, req.size_bytes, resolver.act_footprint(origin.external.row),
          resolver.burst_footprint(origin.external)};
}

}  // namespace Ramulator
