#include "ramulator/dram/pud_location.h"

#include <algorithm>
#include <initializer_list>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>

#include "ramulator/dram/pud_location_internal.h"

namespace Ramulator::PuD {
using namespace LocationDetail;

AddrVec_t ExternalLocation::addr_vec() const {
  auto result = row.bank;
  result.insert(result.end(), {row.row, column.value});
  return result;
}

int LocationResolver::burst_bytes() const {
  return static_cast<int>(profile().bit_to_slot.size() / 8);
}
int LocationResolver::logical_mats() const {
  return profile().chips * profile().mats_per_chip;
}
int LocationResolver::groups() const {
  return static_cast<int>(profile().burst_to_group.size());
}
int64_t LocationResolver::rank_row_bits() const {
  return product({logical_mats(), profile().cells_per_mat_row});
}

void LocationResolver::validate_row(ExternalRow row) const {
  require(row.bank.size() == m_association->bank_levels.size(), "unsupported external hierarchy");
  for (size_t i = 0; i < row.bank.size(); ++i) {
    bound(row.bank[i], m_association->bank_sizes[i], m_association->bank_levels[i].c_str());
  }
  bound(row.row, profile().rows_per_bank, "Row");
}

void LocationResolver::validate_cell(const CellID& c) const {
  const auto& p = profile();
  bound(c.subarray, p.rows_per_bank / p.rows_per_subarray, "Subarray");
  bound(c.local_row, p.rows_per_subarray, "LocalRow");
  validate_row({c.bank, c.subarray * p.rows_per_subarray + c.local_row});
  bound(c.chip, p.chips, "Chip");
  bound(c.mat, p.mats_per_chip, "Mat");
  bound(c.column, p.cells_per_mat_row, "CellColumn");
}

LayoutRegion LocationResolver::layout(ExternalRow row, MatRange mats, std::optional<Group> group) const {
  validate_row(row);
  return {row.bank,
          row.row / profile().rows_per_subarray,
          row.row % profile().rows_per_subarray,
          mats,
          group};
}

ResolvedRegion LocationResolver::resolve(const LayoutRegion& origin) const {
  const auto& p = profile();
  validate_cell(
      {origin.bank, origin.subarray, origin.local_row, 0, 0, 0});
  bound(origin.mats.first, logical_mats(), "first logical mat");
  bound(origin.mats.last, logical_mats(), "last logical mat");
  require(origin.mats.first <= origin.mats.last, "mat range must be non-empty and ordered");
  std::optional<BurstColumn> burst;
  if (origin.group) {
    bound(origin.group->value, groups(), "Group");
    burst = BurstColumn{m_group_to_burst[origin.group->value]};
  }
  ExternalRow row{origin.bank,
                  origin.subarray * p.rows_per_subarray + origin.local_row};
  return {m_association, origin, row, burst,
          product({origin.mats.last - origin.mats.first + 1, origin.group ? p.hffs_per_mat : p.cells_per_mat_row})};
}

CellID LocationResolver::cell_at(const ResolvedRegion& region, int64_t index) const {
  require(region.association == m_association, "foreign profile/routing association");
  // Validate the public descriptor rather than trusting editable cached views.
  auto checked = resolve(region.origin);
  require(checked.external_row == region.external_row && checked.burst == region.burst &&
              checked.cell_count == region.cell_count,
          "inconsistent resolved region");
  bound(index, checked.cell_count, "region cell index");
  const auto& p = profile();
  const auto& o = region.origin;
  int width = o.group ? p.hffs_per_mat : p.cells_per_mat_row;
  int mat = o.mats.first + index / width;
  int column = o.group ? p.group_position_to_column[o.group->value * p.hffs_per_mat + index % width] : index % width;
  CellID cell{o.bank,
              o.subarray, o.local_row, mat / p.mats_per_chip, mat % p.mats_per_chip,
              column};
  // The inverse and scalar authority establish this layout's physical backing.
  return resolve(inverse(cell)).cell;
}

ResolvedRegion LocationResolver::act_footprint(ExternalRow row) const {
  return compute_footprint(row, {0, logical_mats() - 1});
}
ResolvedRegion LocationResolver::burst_footprint(ExternalLocation location) const {
  bound(location.column.value, groups(), "BurstColumn");
  return group_footprint(location.row, {0, logical_mats() - 1}, Group{profile().burst_to_group[location.column.value]});
}
ResolvedRegion LocationResolver::compute_footprint(ExternalRow row, MatRange mats) const {
  return resolve(layout(row, mats, std::nullopt));
}
ResolvedRegion LocationResolver::compute_footprint(ExternalRow row, FullMatTag) const {
  return compute_footprint(row, MatRange{0, logical_mats() - 1});
}
ResolvedRegion LocationResolver::group_footprint(ExternalRow row, MatRange mats, Group group) const {
  return resolve(layout(row, mats, group));
}
bool LocationResolver::directed_neighbors(int source_mat, int destination_mat) const {
  bound(source_mat, logical_mats(), "source logical mat");
  bound(destination_mat, logical_mats(), "destination logical mat");
  return profile().gb_successor[source_mat] == destination_mat;
}

PairedOperand LocationResolver::pair(ResolvedRegion region, std::optional<BurstColumn> column) const {
  // Reuse the canonical region validation, including its retained association.
  cell_at(region, 0);
  if (column) {
    bound(column->value, groups(), "BurstColumn");
    require(!region.burst || column == region.burst, "inconsistent group/burst projection");
  }
  const auto projected_column = column ? column : region.burst;
  const auto& row = region.external_row;
  // Absence stays optional in canonical coordinates. The bare vector
  // projection uses -1 to represent an unspecified Column.
  auto external = ExternalLocation{row, BurstColumn{projected_column ? projected_column->value : -1}}.addr_vec();
  return {std::move(region), std::move(external)};
}

void LocationResolver::validate(const PairedOperand& operand) const {
  require(operand.external.size() == m_association->bank_levels.size() + 2,
          "paired operand requires complete external coordinates");
  std::optional<BurstColumn> column;
  if (operand.external.back() != -1) {
    column = BurstColumn{operand.external.back()};
  }
  require(pair(operand.location, column).external == operand.external, "inconsistent external projection");
}

std::vector<MatSegment> LocationResolver::segment_range(MatRange mats) const {
  bound(mats.first, logical_mats(), "first logical mat");
  bound(mats.last, logical_mats(), "last logical mat");
  require(mats.first <= mats.last, "mat range must be non-empty and ordered");
  int width = profile().mats_per_chip;
  int first_chip = mats.first / width;
  int last_chip = mats.last / width;
  std::vector<MatSegment> segments;
  for (int chip = first_chip; chip <= last_chip; ++chip) {
    segments.push_back(
        {chip, chip == first_chip ? mats.first % width : 0, chip == last_chip ? mats.last % width : width - 1});
  }
  return segments;
}

}  // namespace Ramulator::PuD
