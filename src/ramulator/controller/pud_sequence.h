#ifndef RAMULATOR_CONTROLLER_PUD_SEQUENCE_H
#define RAMULATOR_CONTROLLER_PUD_SEQUENCE_H

#include <cstddef>

#include "ramulator/base/request.h"

namespace Ramulator {

class DRAMSpec;

enum class PuDOccurrenceRole {
  Operand,
  Source,
  Destination,
};

struct PuDOccurrence {
  int command = -1;
  size_t operand_index = 0;
  PuDOccurrenceRole role = PuDOccurrenceRole::Operand;
  size_t index = 0;
  bool terminal = false;
};

enum class PuDOccurrenceAdvance {
  NotIssued,
  Advanced,
  Complete,
};

size_t get_pud_sequence_length(const Request& req);
PuDOccurrence describe_pud_occurrence(const Request& req, size_t occurrence_index, const DRAMSpec& spec);
void initialize_pud_sequence(Request& req, const DRAMSpec& spec);
PuDOccurrenceAdvance observe_pud_command_issue(Request& req, int issued_command, Clk_t clk, const DRAMSpec& spec);
const char* pud_occurrence_role_name(PuDOccurrenceRole role);

}  // namespace Ramulator

#endif  // RAMULATOR_CONTROLLER_PUD_SEQUENCE_H
