#include "ramulator/dram/pud_location.h"

#include <algorithm>
#include <initializer_list>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::PuD {
namespace {
constexpr auto kInitialProfileName = "MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1";

std::vector<int> initial_gb_successors(int chips, int mats_per_chip) {
  std::vector<int> successors(chips * mats_per_chip, -1);
  for (int chip = 0; chip < chips; ++chip) {
    for (int mat = 0; mat + 1 < mats_per_chip; ++mat) {
      int source = chip * mats_per_chip + mat;
      successors[source] = source + 1;
    }
  }
  return successors;
}

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::invalid_argument("PuD location: " + message);
  }
}
void bound(int64_t value, int64_t size, const char* name) {
  require(value >= 0 && value < size, std::string(name) + " out of bounds");
}
int64_t product(std::initializer_list<int64_t> dimensions) {
  int64_t result = 1;
  for (int64_t dimension : dimensions) {
    require(dimension > 0, "dimensions must be positive");
    require(result <= std::numeric_limits<int64_t>::max() / dimension, "capacity overflow");
    result *= dimension;
  }
  return result;
}
std::vector<int> identity(int size) {
  std::vector<int> result(size);
  std::iota(result.begin(), result.end(), 0);
  return result;
}
std::vector<int> inverse_permutation(const std::vector<int>& forward, int64_t size) {
  require(static_cast<int64_t>(forward.size()) == size, "placement table size mismatch");
  std::vector<int> inverse(forward.size(), -1);
  for (size_t i = 0; i < forward.size(); ++i) {
    bound(forward[i], size, "placement table entry");
    require(inverse[forward[i]] == -1, "placement table must be a permutation");
    inverse[forward[i]] = static_cast<int>(i);
  }
  return inverse;
}
}  // namespace

AddrVec_t ExternalLocation::addr_vec() const {
  return {row.channel, row.rank, row.bank_group, row.bank, row.row, column.value};
}

PlacementProfile PlacementProfile::mimdram_ddr4_8gb_x8_v1() {
  // Gate B's modeled chip-major placement; not vendor DDR4 wiring.
  PlacementProfile p;
  p.name = kInitialProfileName;
  p.dq = 8;
  p.prefetch = 8;
  p.channel_width = 64;
  p.organization_columns = 1024;
  p.bank_groups = 4;
  p.banks_per_group = 4;
  p.rows_per_bank = 65536;
  p.chips = 8;
  p.mats_per_chip = 16;
  p.cells_per_mat_row = 512;
  p.hffs_per_mat = 4;
  p.rows_per_subarray = 1024;
  p.rank_counts = {1, 4};
  p.burst_to_group = identity(p.organization_columns / p.prefetch);
  p.bit_to_slot = identity(p.chips * p.mats_per_chip * p.hffs_per_mat);
  p.group_position_to_column = identity(p.cells_per_mat_row);
  p.gb_successor = initial_gb_successors(p.chips, p.mats_per_chip);
  return p;
}

LocationResolver::LocationResolver(PlacementProfile p, const DRAMSpec& spec, MappingContext context) {
  require(!p.name.empty() && !context.address_space.empty(), "profile/address-space association required");
  require(context.channels == 1 && context.channel_mapper == "CacheLineInterleave" &&
              context.address_mapper == "RoBaRaCoCh" && !context.row_remapping && context.reserved_rows_per_bank == 0,
          "unsupported v2 mapper/remapping context");
  require(spec.standard_name == "DDR4" || spec.standard_name == "DDR4_PuD" || spec.standard_name == "DDR4_PuD_Movement",
          "unsupported DDR standard");
  require(spec.level_names == std::vector<std::string>{"Channel", "Rank", "BankGroup", "Bank", "Row", "Column"} &&
              spec.organization.level_sizes.size() == 6,
          "unsupported external hierarchy");
  for (int dimension :
       {p.dq, p.prefetch, p.channel_width, p.organization_columns, p.bank_groups, p.banks_per_group, p.rows_per_bank,
        p.chips, p.mats_per_chip, p.cells_per_mat_row, p.hffs_per_mat, p.rows_per_subarray}) {
    require(dimension > 0, "dimensions must be positive");
  }
  require(!p.rank_counts.empty(), "supported rank counts required");
  // Existing external mappers slice bits: reject unrepresentable dimensions.
  for (int dimension : p.rank_counts) {
    require(dimension > 0 && (dimension & (dimension - 1)) == 0, "invalid supported rank count");
  }
  require(p.organization_columns % p.prefetch == 0 && p.cells_per_mat_row % p.hffs_per_mat == 0 &&
              p.rows_per_bank % p.rows_per_subarray == 0,
          "dimensions require exact division");
  require(product({p.organization_columns, p.dq}) == product({p.mats_per_chip, p.cells_per_mat_row}),
          "chip-row capacity mismatch");
  require(product({p.dq, p.prefetch}) == product({p.mats_per_chip, p.hffs_per_mat}), "chip burst capacity mismatch");
  require(p.organization_columns / p.prefetch == p.cells_per_mat_row / p.hffs_per_mat, "burst/group coverage mismatch");
  require(product({p.chips, p.dq}) == p.channel_width, "rank/channel width mismatch");
  int64_t burst_bits = product({p.prefetch, p.channel_width});
  require(burst_bits % 8 == 0 && burst_bits <= std::numeric_limits<int>::max(),
          "burst width must be byte-exact and indexable");
  for (int dimension : {p.bank_groups, p.banks_per_group, p.rows_per_bank, p.organization_columns, p.prefetch,
                        static_cast<int>(burst_bits / 8)}) {
    require((dimension & (dimension - 1)) == 0, "external mapper requires power-of-two dimensions");
  }
  const auto& sizes = spec.organization.level_sizes;
  require(std::find(p.rank_counts.begin(), p.rank_counts.end(), sizes[1]) != p.rank_counts.end(),
          "unsupported rank replication");
  require(sizes == std::vector<int>{1, sizes[1], p.bank_groups, p.banks_per_group, p.rows_per_bank,
                                    p.organization_columns} &&
              spec.organization.dq == p.dq && spec.internal_prefetch_size == p.prefetch &&
              spec.channel_width == p.channel_width && spec.get_tx_bytes() == burst_bits / 8,
          "profile/DRAM organization mismatch");
  require(!spec.geometry.has_subarrays() || spec.geometry.rows_per_subarray == p.rows_per_subarray,
          "profile/DRAM row subdivision mismatch");
  require(!spec.hffs_per_mat || *spec.hffs_per_mat == p.hffs_per_mat,
          "HFF-only override is inconsistent with the placement profile");
  int64_t capacity_bits = product(
      {sizes[1], p.bank_groups, p.banks_per_group, p.rows_per_bank, p.chips, p.mats_per_chip, p.cells_per_mat_row});
  require(capacity_bits % 8 == 0, "capacity must be byte-exact");
  m_capacity_bytes = capacity_bits / 8;
  m_group_to_burst = inverse_permutation(p.burst_to_group, p.cells_per_mat_row / p.hffs_per_mat);
  m_slot_to_bit = inverse_permutation(p.bit_to_slot, burst_bits);
  m_column_to_group_position = inverse_permutation(p.group_position_to_column, p.cells_per_mat_row);
  int mat_count = p.chips * p.mats_per_chip;  // Bounded by the validated burst slot count.
  require(p.gb_successor.size() == static_cast<size_t>(mat_count), "GB successor table size mismatch");
  for (int target : p.gb_successor) {
    if (target != -1) {
      bound(target, mat_count, "GB successor target");
    }
  }
  // Protect the named initial profile's accepted topology. Replacement software
  // profiles supply their own relation; numeric adjacency is not universal.
  if (p.name == kInitialProfileName) {
    require(p.gb_successor == initial_gb_successors(p.chips, p.mats_per_chip),
            "initial profile requires same-chip forward GB topology without wrap");
  }
  m_association =
      std::make_shared<const LocationAssociation>(LocationAssociation{std::move(p), std::move(context), sizes[1]});
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
  bound(row.channel, 1, "Channel");
  bound(row.rank, m_association->ranks, "Rank");
  bound(row.bank_group, profile().bank_groups, "BankGroup");
  bound(row.bank, profile().banks_per_group, "Bank");
  bound(row.row, profile().rows_per_bank, "Row");
}

void LocationResolver::validate_cell(const CellID& c) const {
  const auto& p = profile();
  bound(c.subarray, p.rows_per_bank / p.rows_per_subarray, "Subarray");
  bound(c.local_row, p.rows_per_subarray, "LocalRow");
  validate_row({c.channel, c.rank, c.bank_group, c.bank, c.subarray * p.rows_per_subarray + c.local_row});
  bound(c.chip, p.chips, "Chip");
  bound(c.mat, p.mats_per_chip, "Mat");
  bound(c.column, p.cells_per_mat_row, "CellColumn");
}

ResolvedBit LocationResolver::resolve(PhysicalBit origin) const {
  bound(origin.byte, m_capacity_bytes, "physical byte");
  bound(origin.bit, 8, "bit within byte");
  const auto& p = profile();
  // Mixed-radix form of Gate B's CacheLineInterleave/RoBaRaCoCh formulas.
  // Retain offset and bit before compacting the external view.
  int offset = origin.byte % burst_bytes();
  int64_t address = origin.byte / burst_bytes();
  int burst = address % groups();
  address /= groups();
  int rank = address % m_association->ranks;
  address /= m_association->ranks;
  int bg = address % p.bank_groups;
  address /= p.bank_groups;
  int bank = address % p.banks_per_group;
  int row = address / p.banks_per_group;
  int slot = p.bit_to_slot[8 * offset + origin.bit];
  int h = slot % p.hffs_per_mat;
  int mat = slot / p.hffs_per_mat;
  int group = p.burst_to_group[burst];
  CellID cell{0,
              rank,
              bg,
              bank,
              row / p.rows_per_subarray,
              row % p.rows_per_subarray,
              mat / p.mats_per_chip,
              mat % p.mats_per_chip,
              p.group_position_to_column[group * p.hffs_per_mat + h]};
  return {m_association, origin, {{0, rank, bg, bank, row}, BurstColumn{burst}}, cell, Group{group}, h};
}

PhysicalBit LocationResolver::inverse(const CellID& cell) const {
  validate_cell(cell);
  const auto& p = profile();
  int position = m_column_to_group_position[cell.column];
  int burst = m_group_to_burst[position / p.hffs_per_mat];
  int slot = (cell.chip * p.mats_per_chip + cell.mat) * p.hffs_per_mat + position % p.hffs_per_mat;
  int bit = m_slot_to_bit[slot];
  int64_t row = cell.subarray * p.rows_per_subarray + cell.local_row;
  int64_t address =
      cell.rank + m_association->ranks * (cell.bank_group + p.bank_groups * (cell.bank + p.banks_per_group * row));
  address = bit / 8 + burst_bytes() * (burst + groups() * address);
  return {address, bit % 8};
}

LayoutRegion LocationResolver::layout(ExternalRow row, MatRange mats, std::optional<Group> group) const {
  validate_row(row);
  return {row.channel,
          row.rank,
          row.bank_group,
          row.bank,
          row.row / profile().rows_per_subarray,
          row.row % profile().rows_per_subarray,
          mats,
          group};
}

ResolvedRegion LocationResolver::resolve(const LayoutRegion& origin) const {
  const auto& p = profile();
  validate_cell(
      {origin.channel, origin.rank, origin.bank_group, origin.bank, origin.subarray, origin.local_row, 0, 0, 0});
  bound(origin.mats.first, logical_mats(), "first logical mat");
  bound(origin.mats.last, logical_mats(), "last logical mat");
  require(origin.mats.first <= origin.mats.last, "mat range must be non-empty and ordered");
  std::optional<BurstColumn> burst;
  if (origin.group) {
    bound(origin.group->value, groups(), "Group");
    burst = BurstColumn{m_group_to_burst[origin.group->value]};
  }
  ExternalRow row{origin.channel, origin.rank, origin.bank_group, origin.bank,
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
  CellID cell{o.channel,  o.rank,      o.bank_group,          o.bank,
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
ResolvedRegion LocationResolver::group_footprint(ExternalRow row, MatRange mats, Group group) const {
  return resolve(layout(row, mats, group));
}
bool LocationResolver::directed_neighbors(int source_mat, int destination_mat) const {
  bound(source_mat, logical_mats(), "source logical mat");
  bound(destination_mat, logical_mats(), "destination logical mat");
  return profile().gb_successor[source_mat] == destination_mat;
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
