#ifndef RAMULATOR_DRAM_PUD_LOCATION_H
#define RAMULATOR_DRAM_PUD_LOCATION_H

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "ramulator/base/type.h"

namespace Ramulator {
struct DRAMSpec;

namespace PuD {

// External compact Column and internal ordered group are deliberately distinct.
struct BurstColumn {
  int value;
  bool operator==(const BurstColumn&) const = default;
};
struct Group {
  int value;
  bool operator==(const Group&) const = default;
};
struct MatRange {
  int first, last;
  bool operator==(const MatRange&) const = default;
};
struct MatSegment {
  int chip, first_local_mat, last_local_mat;
  bool operator==(const MatSegment&) const = default;
};
struct PhysicalBit {
  Addr_t byte;
  int bit;
  bool operator==(const PhysicalBit&) const = default;
};

struct ExternalRow {
  int channel, rank, bank_group, bank, row;
  bool operator==(const ExternalRow&) const = default;
};
struct ExternalLocation {
  ExternalRow row;
  BurstColumn column;
  AddrVec_t addr_vec() const;
  bool operator==(const ExternalLocation&) const = default;
};
struct CellID {
  int channel, rank, bank_group, bank, subarray, local_row, chip, mat, column;
  bool operator==(const CellID&) const = default;
};

// Explicit physical layout union: one bank/subarray row, a contiguous mat range,
// and either whole mat-rows or one ordered group per mat. No scalar anchor is
// invented for a region, and resolving a bit never implicitly widens its extent.
struct LayoutRegion {
  int channel, rank, bank_group, bank, subarray, local_row;
  MatRange mats;
  std::optional<Group> group;
};

struct MappingContext {
  std::string address_space;
  int channels;
  std::string channel_mapper, address_mapper;
  bool row_remapping;
  int reserved_rows_per_bank;
  bool operator==(const MappingContext&) const = default;
};

// Data describing exhaustive, disjoint HFF-width grouping. Table entries are
// identities, never DRAM/SA/HFF values. Other transfer models need a separate
// explicitly justified profile contract (Gate B).
struct PlacementProfile {
  std::string name;
  int dq, prefetch, channel_width, organization_columns;
  int bank_groups, banks_per_group, rows_per_bank;
  int chips, mats_per_chip, cells_per_mat_row, hffs_per_mat, rows_per_subarray;
  std::vector<int> rank_counts;
  // External B -> internal G, common to all participating mats.
  std::vector<int> burst_to_group;
  // Physical burst bit -> (logical_mat * hffs_per_mat + HFF position).
  std::vector<int> bit_to_slot;
  // (G * hffs_per_mat + HFF position) -> mat-local CellColumn/SA position.
  std::vector<int> group_position_to_column;
  // Logical mat -> direct GB destination; -1 denotes no outgoing edge.
  std::vector<int> gb_successor;

  static PlacementProfile mimdram_ddr4_8gb_x8_v1();
};

struct LocationAssociation {
  PlacementProfile profile;
  MappingContext routing;
  int ranks;
};
struct ResolvedBit {
  std::shared_ptr<const LocationAssociation> association;
  PhysicalBit origin;
  ExternalLocation external;
  CellID cell;
  Group group;
  int hff_position;
};
struct ResolvedRegion {
  std::shared_ptr<const LocationAssociation> association;
  LayoutRegion origin;
  ExternalRow external_row;
  // A full mat-row has no single external burst column.
  std::optional<BurstColumn> burst;
  int64_t cell_count;
};

// W1 location-only support. Construction validates the proposed v2 placement
// against an actual DRAMSpec and explicitly supplied mapping context. This does
// not enable v2 requests or install anything in legacy mapping/execution paths.
class LocationResolver {
 public:
  LocationResolver(PlacementProfile profile, const DRAMSpec& spec, MappingContext context);
  const LocationAssociation& association() const {
    return *m_association;
  }
  int64_t capacity_bytes() const {
    return m_capacity_bytes;
  }
  int64_t rank_row_bits() const;
  int burst_bytes() const;
  int logical_mats() const;
  int groups() const;

  ResolvedBit resolve(PhysicalBit origin) const;
  PhysicalBit inverse(const CellID& cell) const;
  ResolvedRegion resolve(const LayoutRegion& origin) const;
  CellID cell_at(const ResolvedRegion& region, int64_t index) const;
  ResolvedRegion act_footprint(ExternalRow row) const;
  ResolvedRegion burst_footprint(ExternalLocation location) const;
  ResolvedRegion compute_footprint(ExternalRow row, MatRange mats) const;
  // Ordered LC endpoint or singleton GB endpoint; pair/request checks belong to W2.
  ResolvedRegion group_footprint(ExternalRow row, MatRange mats, Group group) const;
  bool directed_neighbors(int source_mat, int destination_mat) const;
  // Exact partition of an inclusive logical range, in logical/chip order.
  // Each segment has inclusive local bounds; invalid/empty ranges are rejected.
  std::vector<MatSegment> segment_range(MatRange mats) const;

 private:
  std::shared_ptr<const LocationAssociation> m_association;
  std::vector<int> m_group_to_burst, m_slot_to_bit, m_column_to_group_position;
  int64_t m_capacity_bytes;
  const PlacementProfile& profile() const {
    return m_association->profile;
  }
  void validate_row(ExternalRow row) const;
  void validate_cell(const CellID& cell) const;
  LayoutRegion layout(ExternalRow row, MatRange mats, std::optional<Group> group) const;
};

}  // namespace PuD
}  // namespace Ramulator

#endif
