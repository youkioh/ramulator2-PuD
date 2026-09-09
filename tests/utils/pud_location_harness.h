#ifndef RAMULATOR_TESTS_PUD_LOCATION_HARNESS_H
#define RAMULATOR_TESTS_PUD_LOCATION_HARNESS_H

#include <nanobind/stl/optional.h>

#include "ramulator/dram/pud_location.h"

// Test-only access to W1's location component, with no v2 execution capability.
class LocationResolverUnderTest {
 public:
  LocationResolverUnderTest(nb::dict dram, nb::dict routing, nb::dict overrides) {
    ConfigNode cfg = py_to_confignode(dram);
    auto spec = DRAMSpec::create(cfg["impl"].as<std::string>(), ConfigNode(ConfigNode::Map{{"dram", cfg}}));
    auto p = PuD::PlacementProfile::mimdram_ddr4_8gb_x8_v1();
    std::map<std::string, int*> dimensions{{"dq", &p.dq},
                                           {"prefetch", &p.prefetch},
                                           {"channel_width", &p.channel_width},
                                           {"organization_columns", &p.organization_columns},
                                           {"bank_groups", &p.bank_groups},
                                           {"banks_per_group", &p.banks_per_group},
                                           {"rows_per_bank", &p.rows_per_bank},
                                           {"chips", &p.chips},
                                           {"mats_per_chip", &p.mats_per_chip},
                                           {"cells_per_mat_row", &p.cells_per_mat_row},
                                           {"hffs_per_mat", &p.hffs_per_mat},
                                           {"rows_per_subarray", &p.rows_per_subarray}};
    for (const auto& [key, target] : dimensions) {
      if (overrides.contains(key.c_str())) {
        *target = nb::cast<int>(overrides[key.c_str()]);
      }
    }
    if (overrides.contains("name")) {
      p.name = nb::cast<std::string>(overrides["name"]);
    }
    if (overrides.contains("rank_counts")) {
      p.rank_counts = nb::cast<std::vector<int>>(overrides["rank_counts"]);
    }
    for (auto [key, target] :
         std::map<std::string, std::vector<int>*>{{"burst_to_group", &p.burst_to_group},
                                                  {"bit_to_slot", &p.bit_to_slot},
                                                  {"gb_successor", &p.gb_successor},
                                                  {"group_position_to_column", &p.group_position_to_column}}) {
      if (overrides.contains(key.c_str())) {
        *target = nb::cast<std::vector<int>>(overrides[key.c_str()]);
      }
    }
    auto context = py_to_confignode(routing);
    m_resolver = std::make_shared<PuD::LocationResolver>(
        std::move(p), *spec,
        PuD::MappingContext{context["address_space"].as<std::string>(), context["channels"].as<int>(),
                            context["channel_mapper"].as<std::string>(), context["address_mapper"].as<std::string>(),
                            context["row_remapping"].as<bool>(), context["reserved_rows_per_bank"].as<int>()});
  }

  std::shared_ptr<const PuD::LocationResolver> resolver() const { return m_resolver; }

  static std::vector<int> cell_vector(PuD::CellID c) {
    return {c.channel, c.rank, c.bank_group, c.bank, c.subarray, c.local_row, c.chip, c.mat, c.column};
  }
  static PuD::ExternalRow row(const std::vector<int>& v) {
    if (v.size() != 5) {
      throw std::invalid_argument("expected five external row coordinates");
    }
    return {v[0], v[1], v[2], v[3], v[4]};
  }
  nb::dict resolve(Addr_t address, int bit) const {
    auto r = m_resolver->resolve(PuD::PhysicalBit{address, bit});
    nb::dict result;
    result["external"] = r.external.addr_vec();
    result["cell"] = cell_vector(r.cell);
    result["group"] = r.group.value;
    result["hff"] = r.hff_position;
    result["origin"] = std::vector<int64_t>{r.origin.byte, r.origin.bit};
    result["profile"] = r.association->profile.name;
    result["address_space"] = r.association->routing.address_space;
    return result;
  }
  std::vector<int64_t> inverse(const std::vector<int>& v) const {
    if (v.size() != 9) {
      throw std::invalid_argument("expected nine CellID coordinates");
    }
    auto r = m_resolver->inverse({v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8]});
    return {r.byte, r.bit};
  }
  PuD::ResolvedRegion region(const std::string& kind, const std::vector<int>& coordinates, int first, int last,
                             std::optional<int> selector) const {
    if (kind == "layout") {
      if (coordinates.size() != 6) {
        throw std::invalid_argument("expected six internal row coordinates");
      }
      return m_resolver->resolve(PuD::LayoutRegion{coordinates[0],
                                                   coordinates[1],
                                                   coordinates[2],
                                                   coordinates[3],
                                                   coordinates[4],
                                                   coordinates[5],
                                                   {first, last},
                                                   selector ? std::optional<PuD::Group>{{*selector}} : std::nullopt});
    }
    if (kind == "act") {
      return m_resolver->act_footprint(row(coordinates));
    }
    if (kind == "compute") {
      return m_resolver->compute_footprint(row(coordinates), {first, last});
    }
    if (!selector) {
      throw std::invalid_argument("explicit selector required");
    }
    if (kind == "burst") {
      return m_resolver->burst_footprint({row(coordinates), PuD::BurstColumn{*selector}});
    }
    if (kind == "group") {
      return m_resolver->group_footprint(row(coordinates), {first, last}, PuD::Group{*selector});
    }
    throw std::invalid_argument("unknown footprint");
  }
  nb::dict footprint(const std::string& kind, const std::vector<int>& coordinates, int first, int last,
                     std::optional<int> selector) const {
    auto r = region(kind, coordinates, first, last, selector);
    nb::dict result;
    std::vector<std::vector<int>> cells;
    for (int64_t i = 0; i < r.cell_count; ++i) {
      cells.push_back(cell_vector(m_resolver->cell_at(r, i)));
    }
    result["cells"] = cells;
    result["external_row"] = std::vector<int>{r.external_row.channel, r.external_row.rank, r.external_row.bank_group,
                                              r.external_row.bank, r.external_row.row};
    result["burst"] = r.burst ? nb::cast(r.burst->value) : nb::none();
    result["profile"] = r.association->profile.name;
    result["address_space"] = r.association->routing.address_space;
    return result;
  }
  std::vector<int> region_cell(int64_t index, bool foreign, bool tampered) const {
    auto r = m_resolver->compute_footprint({0, 0, 0, 0, 0}, {0, 0});
    if (foreign) {
      r.association = std::make_shared<const PuD::LocationAssociation>(*r.association);
    }
    if (tampered) {
      r.external_row.row = 1;
    }
    return cell_vector(m_resolver->cell_at(r, index));
  }
  bool neighbors(int source, int destination) const {
    return m_resolver->directed_neighbors(source, destination);
  }
  std::vector<std::vector<int>> segments(int first, int last) const {
    std::vector<std::vector<int>> result;
    for (const auto& segment : m_resolver->segment_range({first, last})) {
      result.push_back({segment.chip, segment.first_local_mat, segment.last_local_mat});
    }
    return result;
  }
  nb::dict info() const {
    const auto& p = m_resolver->association().profile;
    nb::dict result;
    result["name"] = p.name;
    result["capacity_bytes"] = m_resolver->capacity_bytes();
    result["rank_row_bits"] = m_resolver->rank_row_bits();
    result["burst_bytes"] = m_resolver->burst_bytes();
    result["logical_mats"] = m_resolver->logical_mats();
    result["groups"] = m_resolver->groups();
    result["hffs"] = p.hffs_per_mat;
    result["chip_row_bits"] = int64_t{p.mats_per_chip} * p.cells_per_mat_row;
    result["chip_burst_bits"] = p.dq * p.prefetch;
    result["chip_capacity_bits"] =
        int64_t{p.mats_per_chip} * p.cells_per_mat_row * p.rows_per_bank * p.bank_groups * p.banks_per_group;
    return result;
  }

 private:
  std::shared_ptr<const PuD::LocationResolver> m_resolver;
};

inline void bind_pud_location_harness(nb::module_& m) {
  nb::class_<LocationResolverUnderTest>(m, "_LocationResolverUnderTest")
      .def(nb::init<nb::dict, nb::dict, nb::dict>(), nb::arg("dram"), nb::arg("routing"),
           nb::arg("overrides") = nb::dict())
      .def("resolve", &LocationResolverUnderTest::resolve)
      .def("inverse", &LocationResolverUnderTest::inverse)
      .def("footprint", &LocationResolverUnderTest::footprint, nb::arg("kind"), nb::arg("coordinates"),
           nb::arg("first") = 0, nb::arg("last") = 0, nb::arg("selector") = nb::none())
      .def("region_cell", &LocationResolverUnderTest::region_cell, nb::arg("index"), nb::arg("foreign") = false,
           nb::arg("tampered") = false)
      .def("neighbors", &LocationResolverUnderTest::neighbors)
      .def("segments", &LocationResolverUnderTest::segments)
      .def_prop_ro("info", &LocationResolverUnderTest::info);
}

#endif
