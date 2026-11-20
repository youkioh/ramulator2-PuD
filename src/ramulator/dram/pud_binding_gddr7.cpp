#include "ramulator/dram/pud_binding.h"
#include "ramulator/dram/node.h"

namespace Ramulator {
namespace {
class GDDR7PuDBinding final : public PuDBinding {
 public:
  bool uses_bank_array(const DRAMSpec& spec, int cmd) const override {
    // RCK has Channel timing scope but no Bank-array action or prerequisite.
    // G3 retains its column-bus contention and ordinary start/stop behavior.
    return cmd != spec.get_command_id("RCKSTRT") && cmd != spec.get_command_id("RCKSTOP");
  }
  PuDMovementTimingConstraints movement_timing(const DRAMSpec& spec) const override {
    // Raw timing values denote final receptions. Occurrence edges are not
    // serialized Python edges: adjust their first-issue spacing exactly once.
    auto gap = [&](Clk_t interval, const char* before, const char* after) {
      return interval + spec.command_cycles.at(spec.get_command_id(before))
                      - spec.command_cycles.at(spec.get_command_id(after));
    };
    return {
      {Request::Type::LCMOV, 0, 1, gap(spec.get_timing_value("nRCDRD"), "ACT_MOV", "RD_MOV")},
      {Request::Type::LCMOV, 1, 2, gap(spec.get_timing_value("nRTPSB"), "RD_MOV", "PREpb")},
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
      throw std::logic_error("GDDR7 command requires exactly one command bus");
    return {{meta.is_column_command ? 0 : 1, spec.command_cycles.at(cmd)}};
  }
  void publish_shared_timing(DRAMNode& root, int cmd, const AddrVec_t& address, Clk_t clk) const override {
    const auto& spec = *root.m_spec;
    if (cmd != command(spec, PuDCommand::Close)) {
      // PuD identities have only generated bus edges at Channel scope.
      root.update_timing(cmd, address, clk, false);
      return;
    }
    // Invocation PRE shares nPPD, but must not publish conventional Channel
    // PRE->REF recovery or Bank/sibling nRP/nRPD. Occupancy is recorded by Device.
    for (const char* name : {"PREpb", "PREab"}) {
      auto& ready = root.m_cmd_ready_clk.at(spec.get_command_id(name));
      ready = std::max(ready, clk + spec.get_timing_value("nPPD"));
    }
  }
  std::shared_ptr<const PuD::LocationResolver> placement(
      const std::string& profile, const DRAMSpec& spec, const std::string& mapper) const override {
    if (profile != "MIMDRAM_GDDR7_16Gb_x8_v1" ||
        !spec.supports_compute_requests() || !spec.supports_movement_requests())
      throw std::runtime_error("Unsupported GDDR7 PuD placement profile or incomplete primitive capability");
    return std::make_shared<PuD::LocationResolver>(PuD::PlacementProfile::mimdram_gddr7_16gb_x8_v1(),
        spec, PuD::MappingContext{"physical", 1, "CacheLineInterleave", mapper, false, 0});
  }
};
}
const PuDBinding* find_gddr7_pud_binding(const DRAMSpec& spec) {
  static const GDDR7PuDBinding binding;
  return spec.standard_name == "GDDR7_PuD" ? &binding : nullptr;
}
}
