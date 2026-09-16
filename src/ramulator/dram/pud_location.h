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

/*
 * Common PuD substrate (currently bound only to DDR4):
 *
 * PlacementProfile / LocationResolver
 *     -> explicit resolved MatRange
 *     -> PairedOperand / Request
 *     -> GenericDRAM public ingress
 *     -> GenericDDR PuD buffer
 *     -> first-fit E-engine + complete-range allocation
 *     -> resolved occurrence issue
 *     -> terminal PRE / recovery
 *     -> release / accounting / callback
 *
 * Compute construction uses FULL_MAT or an explicit MatRange. Movement uses
 * explicit source/destination ranges and groups. Request/context retain the
 * immutable location authority; Request owns the sole mutable cursor and issue
 * history. T-A consumes resolved targets at issue, so physical target-delivery
 * latency, queues and target-specific C/A contention are not modeled.
 *
 * DRAMNode owns conventional/shared state and timing. PuD phase/timing and
 * terminal recovery are invocation-local for both compute and movement.
 */

/*
 * Local placement contract:
 * Resolver / resolved results -- share --> immutable LocationAssociation
 *                                          (owns profile/routing data)
 * PairedOperand retains the region and checked external projection.
 * BurstColumn and Group are distinct. Modeled placement is not vendor wiring.
 */

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
// Explicit construction-only selection of every logical mat in the resolver's
// profile. The tag is resolved to MatRange immediately and is never retained.
struct FullMatTag {};
inline constexpr FullMatTag FULL_MAT{};
struct MatSegment {
  int chip, first_local_mat, last_local_mat;
  bool operator==(const MatSegment&) const = default;
};
struct PhysicalBit {
  Addr_t byte;
  int bit;
  bool operator==(const PhysicalBit&) const = default;
};

// Actual hierarchy prefix, beginning at Channel. Its extent defines the scope.
using HierarchyIdentity = AddrVec_t;

// Complete actual hierarchy path through Bank. No synthetic Rank/BankGroup coordinates.
// Its names and bounds belong to the retained resolver association.
using BankIdentity = HierarchyIdentity;

struct ExternalRow {
  BankIdentity bank;
  int row;
  bool operator==(const ExternalRow&) const = default;
};
struct ExternalLocation {
  ExternalRow row;
  BurstColumn column;
  AddrVec_t addr_vec() const;
  bool operator==(const ExternalLocation&) const = default;
};
struct CellID {
  BankIdentity bank;
  int subarray, local_row, chip, mat, column;
  bool operator==(const CellID&) const = default;
};

// Explicit physical layout union: one bank/subarray row, a contiguous mat range,
// and either whole mat-rows or one ordered group per mat. No scalar anchor is
// invented for a region, and resolving a bit never implicitly widens its extent.
struct LayoutRegion {
  BankIdentity bank;
  int subarray, local_row;
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
  // DDR4 external-map parameters, consumed only by the DDR4 placement binding.
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
  int ranks;  // DDR4 scalar-map compatibility metadata; not an execution resource.
  std::vector<std::string> bank_levels;
  std::vector<int> bank_sizes;
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

struct PairedOperand {
  ResolvedRegion location;
  AddrVec_t external;
};

// Validates placement against an actual DRAMSpec and explicit mapping context.
// GenericDDR installs this shared authority when the supported profile is selected.
// The sole scalar-map construction/validation binding is currently DDR4
// (pud_location_ddr4.cpp); target dispatch awaits an approved target profile.
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
  ResolvedRegion compute_footprint(ExternalRow row, FullMatTag) const;
  // Ordered LC endpoint or singleton GB endpoint; Request validation checks pairs.
  ResolvedRegion group_footprint(ExternalRow row, MatRange mats, Group group) const;
  // Whole mat-rows have no burst selector (-1 in the command projection).
  // A supplied conventional Column is checked but never narrows that scope.
  PairedOperand pair(ResolvedRegion region, std::optional<BurstColumn> column = std::nullopt) const;
  void validate(const PairedOperand& operand) const;
  void validate_spec(const DRAMSpec& spec) const;
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
