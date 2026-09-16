#include "ramulator/base/request.h"

#include <stdexcept>
#include <algorithm>

namespace Ramulator {

std::vector<PuD::MatSegment> PuD::RequestLocations::mat_footprint() const {
  std::vector<MatSegment> segments;
  for (const auto& operand : operands) {
    for (const auto& segment : resolver->segment_range(operand.location.origin.mats)) {
      segments.push_back(segment);
    }
  }
  std::sort(segments.begin(), segments.end(), [](const auto& a, const auto& b) {
    return a.chip < b.chip || (a.chip == b.chip && a.first_local_mat < b.first_local_mat);
  });
  std::vector<MatSegment> result;
  for (const auto& segment : segments) {
    if (!result.empty() && result.back().chip == segment.chip &&
        segment.first_local_mat <= result.back().last_local_mat + 1) {
      result.back().last_local_mat = std::max(result.back().last_local_mat, segment.last_local_mat);
    } else {
      result.push_back(segment);
    }
  }
  return result;
}

bool PuD::RequestLocations::same_bank(const RequestLocations& other) const {
  const auto& a = operands.at(0).location.origin;
  const auto& b = other.operands.at(0).location.origin;
  return a.bank == b.bank;
}

bool PuD::RequestLocations::conflicts(const RequestLocations& other) const {
  if (!same_bank(other)) return false;
  // Subarrays are capacity units, not independently executable resources.
  if (operands.at(0).location.origin.subarray != other.operands.at(0).location.origin.subarray) return true;
  const auto a = mat_footprint();
  const auto b = other.mat_footprint();
  for (const auto& x : a) for (const auto& y : b) {
    if (x.chip == y.chip && x.first_local_mat <= y.last_local_mat &&
        y.first_local_mat <= x.last_local_mat) return true;
  }
  return false;
}

Request::Request(Addr_t addr, int type) : addr(addr), type_id(type){};

Request::Request(AddrVec_t addr_vec, int type) : addr_vec(std::move(addr_vec)), type_id(type){};

Request::Request(std::vector<AddrVec_t> operands, int type)
    : type_id(type), operands(std::move(operands)) {
  if (is_inherited_pud_request_type(type)) {
    throw std::invalid_argument(
        "PuD compute construction requires resolver-produced paired operands and an explicit target");
  }
}

Request::Request(std::shared_ptr<const PuD::LocationResolver> resolver,
                 std::vector<PuD::PairedOperand> paired, int type) : type_id(type) {
  if (!resolver || !is_pud_request_type(type)) {
    throw std::invalid_argument("PuD request requires a resolver and PuD type");
  }
  for (const auto& operand : paired) {
    resolver->validate(operand);
    operands.push_back(operand.external);
  }
  pud_locations = std::make_shared<const PuD::RequestLocations>(
      PuD::RequestLocations{std::move(resolver), std::move(paired)});
}

Request::Request(Addr_t addr, int type, int source_id, std::function<void(Request&)> callback)
    : addr(addr), type_id(type), source_id(source_id), callback(callback){};

Request::Request(AddrVec_t addr_vec, Cmd_t, int final_cmd) : addr_vec(std::move(addr_vec)), final_command(final_cmd){};

bool is_inherited_pud_request_type(int type_id) {
  switch (type_id) {
    case Request::Type::RowCopy:
    case Request::Type::MAJ3:
    case Request::Type::MAJ5:
    case Request::Type::NOT:
    case Request::Type::NOT_COPY: return true;
    default: return false;
  }
}

bool is_movement_request_type(int type_id) {
  return type_id == Request::Type::LCMOV || type_id == Request::Type::GBMOV;
}

bool is_pud_request_type(int type_id) {
  return is_inherited_pud_request_type(type_id) || is_movement_request_type(type_id);
}

bool is_controller_sequenced_request_type(int type_id) {
  return is_pud_request_type(type_id);
}

bool is_valid_external_request_size(int type_id, int size_bytes, int tx_bytes) {
  if (is_movement_request_type(type_id)) {
    return size_bytes == Request::kMovementSizeBytesNotApplicable;
  }
  return size_bytes > 0 && size_bytes <= tx_bytes;
}

std::optional<size_t> legacy_pud_statistic_slot(int type_id) {
  switch (type_id) {
    case Request::Type::RowCopy: return 0;
    case Request::Type::MAJ3: return 1;
    case Request::Type::MAJ5: return 2;
    case Request::Type::NOT: return 3;
    case Request::Type::NOT_COPY: return 4;
    default: return std::nullopt;
  }
}

const char* legacy_pud_statistic_name(int type_id) {
  switch (type_id) {
    case Request::Type::RowCopy: return "rowcopy";
    case Request::Type::MAJ3: return "maj3";
    case Request::Type::MAJ5: return "maj5";
    case Request::Type::NOT: return "not";
    case Request::Type::NOT_COPY: return "not_copy";
    default: return nullptr;
  }
}

std::optional<size_t> movement_statistic_slot(int type_id) {
  switch (type_id) {
    case Request::Type::LCMOV: return 0;
    case Request::Type::GBMOV: return 1;
    default: return std::nullopt;
  }
}

const char* movement_statistic_name(int type_id) {
  switch (type_id) {
    case Request::Type::LCMOV: return "lcmov";
    case Request::Type::GBMOV: return "gbmov";
    default: return nullptr;
  }
}

const char* request_type_name(int type_id) {
  switch (type_id) {
    case Request::Type::Read: return "Read";
    case Request::Type::Write: return "Write";
    case Request::Type::RowCopy: return "RowCopy";
    case Request::Type::MAJ3: return "MAJ3";
    case Request::Type::MAJ5: return "MAJ5";
    case Request::Type::NOT: return "NOT";
    case Request::Type::NOT_COPY: return "NOT_COPY";
    case Request::Type::LCMOV: return "LC-MOV";
    case Request::Type::GBMOV: return "GB-MOV";
    default: return "Unknown";
  }
}

}  // namespace Ramulator
