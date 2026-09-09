#ifndef RAMULATOR_DRAM_PUD_TARGET_QUEUE_H
#define RAMULATOR_DRAM_PUD_TARGET_QUEUE_H

#include <deque>
#include <map>
#include <tuple>

#include "ramulator/controller/pud_sequence.h"

namespace Ramulator {

class DRAMDevice;
class PuDComputeContext;
class PuDConflictUnderTest;

// W6 simulator FIFO, not pin-accurate queue circuitry. DRAMDevice owns this
// alongside (never inside) PuDComputeContext. Controller protection authorizes
// transport; descriptors do not extend execution lifetime or retain payloads.
class PuDTargetQueues {
 public:
  static constexpr size_t capacity = 8;
  using Chip = std::tuple<int, int, int>;  // Channel, Rank, Chip; shared across Banks.
  struct Descriptor {
    std::weak_ptr<PuDComputeContext> context;
    PuDOccurrence occurrence;
    Clk_t ready_at;  // Target transmission occupies ready_at - 1.
  };
  struct Entry {
    std::shared_ptr<const Descriptor> descriptor;
    PuD::MatSegment segment;
  };

 private:
  friend class DRAMDevice;
  friend class PuDConflictUnderTest;  // Read-only test snapshots.
  std::map<Chip, std::deque<Entry>> m_queues;

  bool can_enqueue(const PuDComputeContext* context, const PuDOccurrence& target) const;
  bool ready(const PuDComputeContext* context, const PuDOccurrence& target, Clk_t clk) const;
  void enqueue(const std::shared_ptr<PuDComputeContext>& context, const PuDOccurrence& target,
               Clk_t ready_at);
  void consume(const PuDOccurrence& target);
};

}  // namespace Ramulator
#endif
