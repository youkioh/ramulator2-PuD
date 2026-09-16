#ifndef RAMULATOR_DRAM_PUD_BINDING_H
#define RAMULATOR_DRAM_PUD_BINDING_H

#include <vector>
#include "ramulator/dram/dram_spec.h"

namespace Ramulator {
class DRAMNode;

// Mechanism roles are independent of a standard's command names/IDs.
// PRADA OC means Offset Cancellation; sensing roles include WL activation.
enum class PuDCommand {
  Activate, ActivateWithOffsetCancellation, ActivateWithSensing,
  ActivateWithSensingAndOffsetCancellation, Invert, Close,
  MoveActivate, MoveRead, MoveWrite,
};

struct PuDOccurrenceTimingConstraint {
  int request_type = -1;
  size_t predecessor = 0;
  size_t following = 0;
  Clk_t delay = 0;
};
using PuDMovementTimingConstraints = std::vector<PuDOccurrenceTimingConstraint>;

struct PuDCommandResource {
  int id;
  Clk_t occupancy;
};

// Only the missing PuD inputs, alongside the existing DRAMSpec. No tick policy,
// Request progress, ownership table or invocation state lives in a binding.
// A target binding must be explicitly supplied; there is no DDR4 fallback.
class PuDBinding {
 public:
  virtual ~PuDBinding() = default;
  virtual int command(const DRAMSpec&, PuDCommand) const = 0;
  virtual const std::vector<std::vector<TimingConsEntry>>& local_timing(const DRAMSpec&) const = 0;
  virtual PuDMovementTimingConstraints movement_timing(const DRAMSpec&) const = 0;
  virtual Clk_t recovery_deadline(const DRAMSpec&, const Request&, Clk_t retirement, bool protected_request) const = 0;
  virtual std::vector<PuDCommandResource> command_resources(const DRAMSpec&, int command) const = 0;
  virtual void publish_shared_timing(DRAMNode&, int command, const AddrVec_t&, Clk_t) const = 0;
  virtual bool conventional_closed(const DRAMSpec&, const DRAMNode&) const = 0;
  virtual bool conventional_drained(const DRAMSpec&, const DRAMNode&) const = 0;
  virtual std::shared_ptr<const PuD::LocationResolver> placement(
      const std::string& profile, const DRAMSpec&, const std::string& mapper) const = 0;
};

const PuDBinding* find_pud_binding(const DRAMSpec&);
const PuDBinding& pud_binding(const DRAMSpec&);
}  // namespace Ramulator
#endif
