#include "ramulator/dram/pud_binding.h"
#include "ramulator/dram/node.h"

namespace Ramulator {
namespace {
class HBM3PuDBinding final : public PuDBinding {
 public:
  PuDMovementTimingConstraints movement_timing(const DRAMSpec& spec) const override {
    // Occurrence-only nominal reception intervals: convert once to issue gaps.
    auto gap = [&](Clk_t interval, const char* before, const char* after) {
      return interval + spec.command_cycles.at(spec.get_command_id(before))
                      - spec.command_cycles.at(spec.get_command_id(after));
    };
    return {
      {Request::Type::LCMOV, 0, 1, gap(spec.get_timing_value("nRCDRD"), "ACT_MOV", "RD_MOV")},
      {Request::Type::LCMOV, 1, 2, gap(spec.get_timing_value("nRTP"), "RD_MOV", "PREpb")},
      {Request::Type::LCMOV, 4, 5, gap(spec.get_timing_value("nRELOC") + spec.get_timing_value("nWR"), "WR_MOV", "PREpb")},
      {Request::Type::GBMOV, 0, 2, gap(spec.get_timing_value("nRAS"), "ACT_MOV", "RD_MOV")},
      {Request::Type::GBMOV, 2, 3, gap(spec.get_timing_value("nRELOC"), "RD_MOV", "WR_MOV")},
      {Request::Type::GBMOV, 3, 4, gap(spec.get_timing_value("nWR"), "WR_MOV", "PREpb")},
    };
  }
  Clk_t recovery_deadline(const DRAMSpec& spec, const Request& req, Clk_t retirement,
                         bool protected_request) const override {
    const Clk_t issue = protected_request ? req.occurrence_issue_history.back() : retirement;
    return issue + spec.command_cycles.at(command(spec, PuDCommand::Close)) - 1 + spec.get_timing_value("nRP");
  }
  std::vector<PuDCommandResource> command_resources(const DRAMSpec& spec, int cmd) const override {
    const auto& meta = spec.command_meta.at(cmd);
    if (meta.is_row_command == meta.is_column_command)
      throw std::logic_error("HBM3 command requires exactly one Channel command bus");
    return {{meta.is_column_command ? 0 : 1, spec.command_cycles.at(cmd)}};
  }
  void publish_shared_timing(DRAMNode& root, int cmd, const AddrVec_t& address, Clk_t clk) const override {
    const auto& spec = *root.m_spec;
    // Channel occupancy; never descend into Bank-local phase/recovery history.
    root.update_timing(cmd, address, clk, false);
    if (cmd != command(spec, PuDCommand::Close)) return;
    auto& pc = *root.m_child_nodes.at(address.at(spec.get_level_id("PseudoChannel")));
    // Invocation PRE shares only the addressed PC's nPPD. Publishing its full
    // conventional PRE timing would incorrectly block disjoint invocations/REF.
    for (const char* name : {"PREpb", "PREab"}) {
      auto& ready = pc.m_cmd_ready_clk.at(spec.get_command_id(name));
      ready = std::max(ready, clk + spec.get_timing_value("nPPD"));
    }
  }
  std::shared_ptr<const PuD::LocationResolver> placement(
      const std::string& profile, const DRAMSpec& spec, const std::string& mapper) const override {
    if (profile != "MIMDRAM_HBM3_8Gb_8hi_v1" ||
        !spec.supports_compute_requests() || !spec.supports_movement_requests())
      throw std::runtime_error("Unsupported HBM3 PuD placement profile or incomplete primitive capability");
    return std::make_shared<PuD::LocationResolver>(PuD::PlacementProfile::mimdram_hbm3_8gb_8hi_v1(),
        spec, PuD::MappingContext{"physical", 1, "CacheLineInterleave", mapper, false, 0});
  }
};
}
const PuDBinding* find_hbm3_pud_binding(const DRAMSpec& spec) {
  static const HBM3PuDBinding binding;
  return spec.standard_name == "HBM3_PuD" ? &binding : nullptr;
}
}
