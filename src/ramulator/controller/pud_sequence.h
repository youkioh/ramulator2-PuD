#ifndef RAMULATOR_CONTROLLER_PUD_SEQUENCE_H
#define RAMULATOR_CONTROLLER_PUD_SEQUENCE_H

#include <array>
#include <cstddef>

#include "ramulator/base/request.h"
#include "ramulator/dram/pud_binding.h"

namespace Ramulator {

class DRAMSpec;

/*
 * Request cursor/history + operands (request.h)
 *                  |
 *                  v
 *        +-------------------------+
 *        | PuDOccurrence           | <-- YOU ARE HERE
 *        | current occurrence view |
 *        +------------+------------+
 *                     |
 *                     v
 *        Device dispatch + PuDExecutionContext (device.h)
 *
 * Movement Request history ---> +-------------------------+
 *                               | PuDMovementState        |
 *                               | derived view only       |
 *                               +-------------------------+
 * Views retain placement, never independent progress. Request owns the cursor;
 * Context owns only protocol phase; Controller owns protection through recovery.
 * Movement sequence_active describes schedulable progress, not resource lifetime.
 */

enum class PuDOccurrenceRole {
  Operand,
  Source,
  Destination,
};

struct PuDOccurrence {
  int command = -1;
  PuDCommand action = PuDCommand::Close;
  size_t operand_index = 0;
  PuDOccurrenceRole role = PuDOccurrenceRole::Operand;
  size_t index = 0;
  bool terminal = false;
  std::shared_ptr<const PuD::RequestLocations> locations;
  const PuD::PairedOperand* location() const {
    return locations ? &locations->operands.at(operand_index) : nullptr;
  }
};

// A view of the retained footprint-local movement invocation, not another state
// machine/cursor. Endpoint identity remains in the Request's paired operands.
struct PuDMovementState {
  bool sequence_active = false;
  bool source_active = false;
  bool destination_active = false;
  bool source_valid = false;
  std::shared_ptr<const PuD::RequestLocations> locations;
};
PuDMovementState describe_pud_movement_state(const Request& req);

enum class PuDOccurrenceAdvance {
  NotIssued,
  Advanced,
  Complete,
};

size_t get_pud_sequence_length(const Request& req);
PuDOccurrence describe_pud_occurrence(const Request& req, size_t occurrence_index, const DRAMSpec& spec);
void initialize_pud_sequence(Request& req, const DRAMSpec& spec);
PuDOccurrenceAdvance observe_pud_command_issue(Request& req, int issued_command, Clk_t clk, const DRAMSpec& spec);
PuDMovementTimingConstraints make_movement_timing_constraints(const DRAMSpec& spec);
bool check_pud_occurrence_timing(
    const Request& req, Clk_t clk,
    const PuDMovementTimingConstraints& constraints);
// PuD dispatch interprets binding-selected local edges against this Request's
// occurrence history. Device must not also publish them into shared history.
bool check_pud_local_timing(const Request& req, Clk_t clk, const DRAMSpec& spec);
const char* pud_occurrence_role_name(PuDOccurrenceRole role);

}  // namespace Ramulator

#endif  // RAMULATOR_CONTROLLER_PUD_SEQUENCE_H
