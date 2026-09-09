#include "ramulator/dram/pud_target_queue.h"

#include "ramulator/dram/device.h"

namespace Ramulator {

bool PuDTargetQueues::can_enqueue(const PuDComputeContext* context, const PuDOccurrence& target) const {
  const auto& origin = target.location()->location.origin;
  for (const auto& segment : target.locations->resolver->segment_range(origin.mats)) {
    const auto it = m_queues.find({origin.channel, origin.rank, segment.chip});
    if (it == m_queues.end()) continue;
    if (it->second.size() >= capacity) return false;
    for (const auto& entry : it->second) {
      if (entry.descriptor->context.lock().get() == context &&
          entry.descriptor->occurrence.index == target.index) return false;
    }
  }
  return true;
}

bool PuDTargetQueues::ready(const PuDComputeContext* context, const PuDOccurrence& target, Clk_t clk) const {
  const auto& origin = target.location()->location.origin;
  for (const auto& segment : target.locations->resolver->segment_range(origin.mats)) {
    const auto it = m_queues.find({origin.channel, origin.rank, segment.chip});
    if (it == m_queues.end() || it->second.empty()) return false;
    const auto& head = it->second.front();
    const auto& descriptor = *head.descriptor;
    const auto& occurrence = descriptor.occurrence;
    if (descriptor.context.lock().get() != context || descriptor.ready_at > clk ||
        occurrence.locations != target.locations || occurrence.index != target.index ||
        occurrence.command != target.command || occurrence.operand_index != target.operand_index ||
        head.segment != segment) return false;
  }
  return true;
}

void PuDTargetQueues::enqueue(const std::shared_ptr<PuDComputeContext>& context, const PuDOccurrence& target,
                              Clk_t ready_at) {
  const auto descriptor = std::make_shared<const Descriptor>(Descriptor{context, target, ready_at});
  const auto& origin = target.location()->location.origin;
  for (const auto& segment : target.locations->resolver->segment_range(origin.mats)) {
    m_queues[{origin.channel, origin.rank, segment.chip}].push_back({descriptor, segment});
  }
}

void PuDTargetQueues::consume(const PuDOccurrence& target) {
  const auto& origin = target.location()->location.origin;
  for (const auto& segment : target.locations->resolver->segment_range(origin.mats)) {
    m_queues.at({origin.channel, origin.rank, segment.chip}).pop_front();
  }
}

}  // namespace Ramulator
