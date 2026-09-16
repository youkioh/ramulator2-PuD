#include "ramulator/dram/pud_binding.h"

#include "ramulator/dram/node.h"

namespace Ramulator {
namespace {
// The accepted DDR4 calibration/geometry remain in its Python declarations and
// placement binding. No GDDR7/HBM3 profile or timing is registered here.
class DDR4PuDBinding final : public PuDBinding {
 public:
  int command(const DRAMSpec& spec, PuDCommand role) const override {
    switch (role) {
      case PuDCommand::Activate: return spec.get_command_id("ACT_PUD");
      case PuDCommand::ActivateWithOffsetCancellation: return spec.get_command_id("ACT_PUD_OC");
      case PuDCommand::ActivateWithSensing: return spec.get_command_id("ACT_PUD_S");
      case PuDCommand::ActivateWithSensingAndOffsetCancellation: return spec.get_command_id("ACT_PUD_S_OC");
      case PuDCommand::Invert: return spec.get_command_id("N");
      case PuDCommand::Close: return spec.get_command_id("PREpb");
      case PuDCommand::MoveActivate: return spec.get_command_id("ACT_MOV");
      case PuDCommand::MoveRead: return spec.get_command_id("RD_MOV");
      case PuDCommand::MoveWrite: return spec.get_command_id("WR_MOV");
    }
    throw std::logic_error("Unknown PuD mechanism role");
  }
  const std::vector<std::vector<TimingConsEntry>>& local_timing(const DRAMSpec& spec) const override {
    // Bank declarations supply numeric local edges; they are never published
    // into shared Bank history by invocation dispatch.
    return spec.timing_cons.at(spec.get_level_id("Bank"));
  }
  PuDMovementTimingConstraints movement_timing(const DRAMSpec& spec) const override {
    return {
        {Request::Type::LCMOV, 0, 1, spec.get_timing_value("nRCD")},
        {Request::Type::LCMOV, 1, 2, spec.get_timing_value("nRTP")},
        {Request::Type::LCMOV, 4, 5, spec.get_timing_value("nRELOC") + spec.get_timing_value("nWR")},
        {Request::Type::GBMOV, 0, 2, spec.get_timing_value("nRAS")},
        {Request::Type::GBMOV, 2, 3, spec.get_timing_value("nRELOC")},
        {Request::Type::GBMOV, 3, 4, spec.get_timing_value("nWR")},
    };
  }
  Clk_t recovery_deadline(const DRAMSpec& spec, const Request& req, Clk_t retirement,
                           bool protected_request) const override {
    const Clk_t anchor = protected_request ? req.occurrence_issue_history.back() : retirement;
    return anchor + spec.get_timing_value("nRP");
  }
  std::vector<PuDCommandResource> command_resources(const DRAMSpec& spec, int cmd) const override {
    // DDR4 has one combined command bus. Ordinary arbitration is unchanged.
    return {{0, spec.command_cycles.at(cmd)}};
  }
  void publish_shared_timing(DRAMNode& root, int cmd, const AddrVec_t& address, Clk_t clk) const override {
    // Channel only. Local PRE recovery and PRADA/movement edges must not enter
    // shared Bank/Rank history. PuD ACTs do not publish nRRD/nFAW current edges.
    // Incoming conventional PRE/AP/REF timing is still checked through the tree.
    root.update_timing(cmd, address, clk, false);
  }
  bool conventional_closed(const DRAMSpec& spec, const DRAMNode& bank) const override {
    return bank.m_state == spec.get_state_id("Closed");
  }
  bool conventional_drained(const DRAMSpec& spec, const DRAMNode& bank) const override {
    return conventional_closed(spec, bank) && bank.m_row_state.empty();
  }
  std::shared_ptr<const PuD::LocationResolver> placement(
      const std::string& profile, const DRAMSpec& spec, const std::string& mapper) const override {
    if (profile != "MIMDRAM_DDR4_8Gb_x8_v1" ||
        !spec.supports_compute_requests() || !spec.supports_movement_requests()) {
      throw std::runtime_error("Unsupported PuD placement profile or incomplete unified-substrate capability");
    }
    return std::make_shared<PuD::LocationResolver>(
        PuD::PlacementProfile::mimdram_ddr4_8gb_x8_v1(), spec,
        PuD::MappingContext{"physical", 1, "CacheLineInterleave", mapper, false, 0});
  }
};
}  // namespace

const PuDBinding* find_pud_binding(const DRAMSpec& spec) {
  static const DDR4PuDBinding ddr4;
  if (spec.standard_name == "DDR4_PuD" || spec.standard_name == "DDR4_PuD_Movement") return &ddr4;
  return nullptr;
}
const PuDBinding& pud_binding(const DRAMSpec& spec) {
  const auto* binding = find_pud_binding(spec);
  if (!binding) throw std::logic_error("No PuD binding for " + spec.standard_name);
  return *binding;
}
}  // namespace Ramulator
