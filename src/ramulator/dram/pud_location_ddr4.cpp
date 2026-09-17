// Coordinated placement validation and provisional RoBaRaCoCh scalar mapping.
// The DDR4 profile and its public compatibility projection remain unchanged.
#include "ramulator/dram/pud_location.h"

#include <algorithm>
#include <numeric>

#include "ramulator/dram/dram_spec.h"
#include "ramulator/dram/pud_location_internal.h"

namespace Ramulator::PuD {
using namespace LocationDetail;
namespace {
constexpr auto kInitialProfileName = "MIMDRAM-DDR4_8Gb_x8 modeled placement profile v1";
constexpr auto kGDDR7ProfileName = "MIMDRAM-GDDR7_16Gb_x8 modeled placement profile v1";
constexpr auto kHBM3ProfileName = "MIMDRAM-HBM3_8Gb_8hi modeled placement profile v1";

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

std::vector<int> identity(int size) {
  std::vector<int> result(size);
  std::iota(result.begin(), result.end(), 0);
  return result;
}
}  // namespace

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

PlacementProfile PlacementProfile::mimdram_gddr7_16gb_x8_v1() {
  // Accepted G1: one x8 channel slice; eight transfer positions are a
  // derived HFF-equivalent model, not measured GDDR7 circuitry or GPU wiring.
  PlacementProfile p{};
  p.name = kGDDR7ProfileName;
  p.dq = 8;
  p.prefetch = 32;
  p.channel_width = 8;
  p.organization_columns = 2048;
  p.banks_per_channel = 16;
  p.rows_per_bank = 16384;
  p.chips = 1;
  p.mats_per_chip = 32;
  p.cells_per_mat_row = 512;
  p.hffs_per_mat = 8;
  p.rows_per_subarray = 512;
  p.burst_to_group = identity(64);
  p.bit_to_slot = identity(256);
  p.group_position_to_column = identity(512);
  p.gb_successor = initial_gb_successors(1, 32);
  return p;
}

PlacementProfile PlacementProfile::mimdram_hbm3_8gb_8hi_v1() {
  // Accepted representative older-HBM geometry and logical transfer positions;
  // chips=1 denotes one participating 32-bit slice, not a physical stack die.
  PlacementProfile p{};
  p.name = kHBM3ProfileName;
  p.dq = 32;
  p.prefetch = 8;
  p.channel_width = 32;
  p.organization_columns = 256;
  p.pseudochannels = 2;
  p.sids_per_pc = 2;
  p.bank_groups = 4;
  p.banks_per_group = 4;
  p.rows_per_bank = 8192;
  p.chips = 1;
  p.mats_per_chip = 16;
  p.cells_per_mat_row = 512;
  p.hffs_per_mat = 16;
  p.rows_per_subarray = 512;
  p.burst_to_group = identity(32);
  p.bit_to_slot = identity(256);
  p.group_position_to_column = identity(512);
  p.gb_successor = initial_gb_successors(1, 16);
  return p;
}

LocationResolver::LocationResolver(PlacementProfile p, const DRAMSpec& spec, MappingContext context) {
  require(!p.name.empty() && !context.address_space.empty(), "profile/address-space association required");
  require(context.channels > 0 && (context.channels & (context.channels - 1)) == 0 &&
              context.interleave_bits == 0 && context.channel_mapper == "CacheLineInterleave" &&
              context.address_mapper == "RoBaRaCoCh" && !context.row_remapping && context.reserved_rows_per_bank == 0,
          "unsupported PuD mapper/remapping context");
  const bool gddr7 = spec.standard_name == "GDDR7" || spec.standard_name == "GDDR7_PuD";
  const bool hbm3 = spec.standard_name == "HBM3" || spec.standard_name == "HBM3_PuD";
  require(hbm3 || gddr7 || spec.standard_name == "DDR4" || spec.standard_name == "DDR4_PuD" || spec.standard_name == "DDR4_PuD_Movement",
          "unsupported DDR standard");
  const std::vector<std::string> levels = hbm3
      ? std::vector<std::string>{"Channel", "PseudoChannel", "Sid", "BankGroup", "Bank", "Row", "Column"}
      : gddr7
      ? std::vector<std::string>{"Channel", "Bank", "Row", "Column"}
      : std::vector<std::string>{"Channel", "Rank", "BankGroup", "Bank", "Row", "Column"};
  const int bank_extent = levels.size() - 2;
  require(spec.level_names == levels && spec.organization.level_sizes.size() == levels.size(),
          "unsupported external hierarchy");
  for (int dimension :
       {p.dq, p.prefetch, p.channel_width, p.organization_columns, p.rows_per_bank,
        p.chips, p.mats_per_chip, p.cells_per_mat_row, p.hffs_per_mat, p.rows_per_subarray}) {
    require(dimension > 0, "dimensions must be positive");
  }
  require(hbm3 || gddr7 || !p.rank_counts.empty(), "supported rank counts required");
  if (hbm3) {
    require(p.rank_counts.empty() && p.banks_per_channel == 0, "HBM3 has no Rank");
    require(p.pseudochannels > 0 && p.sids_per_pc > 0, "HBM3 PC/Sid dimensions must be positive");
    for (int size : {p.pseudochannels, p.sids_per_pc})
      require((size & (size - 1)) == 0, "external mapper requires power-of-two dimensions");
  } else {
    require(p.pseudochannels == 0 && p.sids_per_pc == 0, "non-HBM profile has no PC/Sid");
  }
  if (gddr7) {
    require(p.banks_per_channel > 0, "dimensions must be positive");
    require(p.bank_groups == 0 && p.banks_per_group == 0 && p.rank_counts.empty(),
            "GDDR7 has no Rank or BankGroup");
  } else {
    require(p.bank_groups > 0 && p.banks_per_group > 0, "dimensions must be positive");
  }
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
  for (int dimension : {gddr7 ? p.banks_per_channel : p.bank_groups,
                        gddr7 ? p.banks_per_channel : p.banks_per_group, p.rows_per_bank, p.organization_columns, p.prefetch,
                        static_cast<int>(burst_bits / 8)}) {
    require((dimension & (dimension - 1)) == 0, "external mapper requires power-of-two dimensions");
  }
  const auto& sizes = spec.organization.level_sizes;
  require(hbm3 || gddr7 || std::find(p.rank_counts.begin(), p.rank_counts.end(), sizes[1]) != p.rank_counts.end(),
          "unsupported rank replication");
  const std::vector<int> expected_sizes = hbm3
      ? std::vector<int>{1, p.pseudochannels, p.sids_per_pc, p.bank_groups, p.banks_per_group, p.rows_per_bank, p.organization_columns}
      : gddr7
      ? std::vector<int>{1, p.banks_per_channel, p.rows_per_bank, p.organization_columns}
      : std::vector<int>{1, sizes[1], p.bank_groups, p.banks_per_group, p.rows_per_bank, p.organization_columns};
  require(sizes == expected_sizes &&
              spec.organization.dq == p.dq && spec.internal_prefetch_size == p.prefetch &&
              spec.channel_width == p.channel_width && spec.get_tx_bytes() == burst_bits / 8,
          "profile/DRAM organization mismatch");
  require(!spec.geometry.has_subarrays() || spec.geometry.rows_per_subarray == p.rows_per_subarray,
          "profile/DRAM row subdivision mismatch");
  require(!spec.hffs_per_mat || *spec.hffs_per_mat == p.hffs_per_mat,
          "HFF-only override is inconsistent with the placement profile");
  int64_t capacity_bits = product({p.rows_per_bank, p.chips, p.mats_per_chip, p.cells_per_mat_row});
  for (int i = 0; i < bank_extent; ++i) capacity_bits = product({capacity_bits, sizes[i]});
  require(capacity_bits % 8 == 0, "capacity must be byte-exact");
  m_capacity_bytes = product({capacity_bits / 8, context.channels});
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
  if (p.name == kInitialProfileName || p.name == kGDDR7ProfileName || p.name == kHBM3ProfileName) {
    require(p.gb_successor == initial_gb_successors(p.chips, p.mats_per_chip),
            "initial profile requires same-chip forward GB topology without wrap");
  }
  std::vector<int> bank_sizes(sizes.begin(), sizes.begin() + bank_extent);
  bank_sizes[0] = context.channels;
  m_association =
      std::make_shared<const LocationAssociation>(LocationAssociation{std::move(p), std::move(context), (hbm3 || gddr7) ? 0 : sizes[1],
          {levels.begin(), levels.begin() + bank_extent}, std::move(bank_sizes)});
}

ResolvedBit LocationResolver::resolve(PhysicalBit origin) const {
  bound(origin.byte, m_capacity_bytes, "physical byte");
  bound(origin.bit, 8, "bit within byte");
  const auto& p = profile();
  // Mixed-radix form of Gate B's CacheLineInterleave/RoBaRaCoCh formulas.
  // Retain offset and bit before compacting the external view.
  int offset = origin.byte % burst_bytes();
  int64_t address = origin.byte / burst_bytes();
  const int channel = address % m_association->routing.channels;
  address /= m_association->routing.channels;
  int burst = address % groups();
  address /= groups();
  BankIdentity bank(m_association->bank_sizes.size(), 0);
  bank[0] = channel;
  for (size_t i = 1; i < bank.size(); ++i) {
    bank[i] = address % m_association->bank_sizes[i];
    address /= m_association->bank_sizes[i];
  }
  int row = address;
  int slot = p.bit_to_slot[8 * offset + origin.bit];
  int h = slot % p.hffs_per_mat;
  int mat = slot / p.hffs_per_mat;
  int group = p.burst_to_group[burst];
  CellID cell{bank,
              row / p.rows_per_subarray,
              row % p.rows_per_subarray,
              mat / p.mats_per_chip,
              mat % p.mats_per_chip,
              p.group_position_to_column[group * p.hffs_per_mat + h]};
  return {m_association, origin, {{bank, row}, BurstColumn{burst}}, cell, Group{group}, h};
}

PhysicalBit LocationResolver::inverse(const CellID& cell) const {
  validate_cell(cell);
  const auto& p = profile();
  int position = m_column_to_group_position[cell.column];
  int burst = m_group_to_burst[position / p.hffs_per_mat];
  int slot = (cell.chip * p.mats_per_chip + cell.mat) * p.hffs_per_mat + position % p.hffs_per_mat;
  int bit = m_slot_to_bit[slot];
  int64_t row = cell.subarray * p.rows_per_subarray + cell.local_row;
  int64_t address = row;
  for (size_t i = cell.bank.size(); i-- > 1;) {
    address = cell.bank[i] + m_association->bank_sizes[i] * address;
  }
  address = bit / 8 + burst_bytes() *
      (cell.bank[0] + m_association->routing.channels * (burst + groups() * address));
  return {address, bit % 8};
}

void LocationResolver::validate_spec(const DRAMSpec& spec) const {
  // Configuration validation uses the same profile contract as initial construction.
  LocationResolver checked(profile(), spec, m_association->routing);
  require(checked.association().ranks == m_association->ranks, "profile/rank context mismatch");
}

}  // namespace Ramulator::PuD
