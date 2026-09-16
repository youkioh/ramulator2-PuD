#include "ramulator/controller/pud_sequence.h"

#include <fmt/format.h>
#include <stdexcept>

#include "ramulator/dram/dram_spec.h"
#include "ramulator/memory_system/pud_request_routing.h"

namespace Ramulator {

namespace {

void configure_pud_occurrence(Request& req, const DRAMSpec& spec) {
  const auto occurrence = describe_pud_occurrence(req, req.occurrence_index, spec);
  req.addr_vec = req.operands[occurrence.operand_index];
  req.command = -1;
  req.final_command = occurrence.command;
}

PuDOccurrence make_occurrence(const DRAMSpec& spec, const char* command_name, size_t operand_index,
                              PuDOccurrenceRole role, size_t index, size_t sequence_length) {
  return {
      .command = spec.get_command_id(command_name),
      .operand_index = operand_index,
      .role = role,
      .index = index,
      .terminal = index + 1 == sequence_length,
  };
}

}  // namespace

size_t get_pud_sequence_length(const Request& req) {
  switch (req.type_id) {
    case Request::Type::RowCopy:
    case Request::Type::MAJ3:
    case Request::Type::MAJ5:
      return req.operands.size() + 1;
    case Request::Type::NOT:
      return 3;
    case Request::Type::NOT_COPY:
      return 4;
    case Request::Type::LCMOV:
      return 6;
    case Request::Type::GBMOV:
      return 5;
    default:
      throw std::logic_error(fmt::format("Cannot describe controller sequence for request type {}", req.type_id));
  }
}

PuDMovementState describe_pud_movement_state(const Request& req) {
  if (!is_movement_request_type(req.type_id)) {
    throw std::logic_error("Movement state requires LC-MOV or GB-MOV");
  }
  const auto length = get_pud_sequence_length(req);
  const auto cursor = req.occurrence_index;
  if (cursor > length || req.occurrence_issue_history.size() != length) {
    throw std::logic_error("Inconsistent retained movement context");
  }
  for (size_t i = 0; i < length; ++i) {
    if ((req.occurrence_issue_history[i] != Request::kOccurrenceNotIssued) != (i < cursor)) {
      throw std::logic_error("Inconsistent retained movement history");
    }
  }
  if (req.pud_locations) validate_pud_pairs(req);
  const bool lc = req.type_id == Request::Type::LCMOV;
  return {
      .sequence_active = cursor > 0 && cursor < length,
      .source_active = cursor > 0 && cursor < (lc ? 3u : length),
      .destination_active = cursor >= (lc ? 4u : 2u) && cursor < length,
      .source_valid = cursor >= (lc ? 2u : 3u) && cursor < (lc ? 5u : 4u),
      .locations = req.pud_locations,
  };
}

static PuDOccurrence describe_occurrence(const Request& req, size_t occurrence_index, const DRAMSpec& spec) {
  const size_t sequence_length = get_pud_sequence_length(req);
  if (occurrence_index >= sequence_length) {
    throw std::logic_error(fmt::format("{} occurrence {} is outside [0, {})", request_type_name(req.type_id),
                                       occurrence_index, sequence_length));
  }

  if (req.operands.empty()) {
    throw std::logic_error(fmt::format("{} sequence has no operands", request_type_name(req.type_id)));
  }
  if (is_movement_request_type(req.type_id) && req.operands.size() != 2) {
    throw std::logic_error(fmt::format("{} sequence requires exactly two operands, got {}",
                                       request_type_name(req.type_id), req.operands.size()));
  }

  if (req.type_id == Request::Type::LCMOV) {
    static constexpr const char* kCommands[] = {"ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"};
    static constexpr size_t kOperands[] = {0, 0, 0, 1, 1, 1};
    const auto role = occurrence_index < 3 ? PuDOccurrenceRole::Source : PuDOccurrenceRole::Destination;
    return make_occurrence(spec, kCommands[occurrence_index], kOperands[occurrence_index], role, occurrence_index,
                           sequence_length);
  }

  if (req.type_id == Request::Type::GBMOV) {
    static constexpr const char* kCommands[] = {"ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"};
    static constexpr size_t kOperands[] = {0, 1, 0, 1, 1};
    static constexpr PuDOccurrenceRole kRoles[] = {
        PuDOccurrenceRole::Source,      PuDOccurrenceRole::Destination, PuDOccurrenceRole::Source,
        PuDOccurrenceRole::Destination, PuDOccurrenceRole::Destination,
    };
    return make_occurrence(spec, kCommands[occurrence_index], kOperands[occurrence_index], kRoles[occurrence_index],
                           occurrence_index, sequence_length);
  }

  if (req.type_id == Request::Type::NOT) {
    const char* command = occurrence_index == 0 ? "ACT_PUD_S_OC" : occurrence_index == 1 ? "N" : "PREpb";
    return make_occurrence(spec, command, 0, PuDOccurrenceRole::Operand, occurrence_index, sequence_length);
  }

  if (req.type_id == Request::Type::NOT_COPY) {
    static constexpr const char* kCommands[] = {"ACT_PUD_S_OC", "N", "ACT_PUD", "PREpb"};
    static constexpr size_t kOperands[] = {0, 0, 1, 1};
    return make_occurrence(spec, kCommands[occurrence_index], kOperands[occurrence_index],
                           PuDOccurrenceRole::Operand, occurrence_index, sequence_length);
  }

  if (occurrence_index + 1 == sequence_length) {
    return make_occurrence(spec, "PREpb", req.operands.size() - 1, PuDOccurrenceRole::Operand, occurrence_index,
                           sequence_length);
  }

  const char* command = nullptr;
  if (req.type_id == Request::Type::RowCopy) {
    command = occurrence_index == 0 ? "ACT_PUD_S_OC" : "ACT_PUD";
  } else if (req.type_id == Request::Type::MAJ3 || req.type_id == Request::Type::MAJ5) {
    if (occurrence_index == 0) {
      command = "ACT_PUD_OC";
    } else if (occurrence_index + 1 == req.operands.size()) {
      command = "ACT_PUD_S";
    } else {
      command = "ACT_PUD";
    }
  }

  if (command == nullptr) {
    throw std::logic_error(fmt::format("Cannot describe PuD sequence for request type {}", req.type_id));
  }
  return make_occurrence(spec, command, occurrence_index, PuDOccurrenceRole::Operand, occurrence_index,
                         sequence_length);
}

PuDOccurrence describe_pud_occurrence(const Request& req, size_t occurrence_index, const DRAMSpec& spec) {
  if (is_inherited_pud_request_type(req.type_id) && !req.pud_locations) {
    throw std::logic_error("PuD compute sequence requires canonical resolved locations");
  }
  if (req.pud_locations) {
    validate_pud_pairs(req);
  }
  auto occurrence = describe_occurrence(req, occurrence_index, spec);
  occurrence.locations = req.pud_locations;
  return occurrence;
}

void initialize_pud_sequence(Request& req, const DRAMSpec& spec) {
  const size_t sequence_length = get_pud_sequence_length(req);
  req.occurrence_index = 0;
  req.occurrence_issue_history.assign(sequence_length, Request::kOccurrenceNotIssued);
  configure_pud_occurrence(req, spec);
}

PuDOccurrenceAdvance observe_pud_command_issue(Request& req, int issued_command, Clk_t clk, const DRAMSpec& spec) {
  if (issued_command != req.final_command) {
    return PuDOccurrenceAdvance::NotIssued;
  }

  const size_t sequence_length = get_pud_sequence_length(req);
  if (req.occurrence_index >= sequence_length || req.occurrence_issue_history.size() != sequence_length) {
    throw std::logic_error(fmt::format("{} has inconsistent occurrence context: cursor {}, history {}, sequence {}",
                                       request_type_name(req.type_id), req.occurrence_index,
                                       req.occurrence_issue_history.size(), sequence_length));
  }
  if (req.occurrence_issue_history[req.occurrence_index] != Request::kOccurrenceNotIssued) {
    throw std::logic_error(
        fmt::format("{} occurrence {} was already issued", request_type_name(req.type_id), req.occurrence_index));
  }

  req.occurrence_issue_history[req.occurrence_index] = clk;
  req.occurrence_index++;
  if (req.occurrence_index == sequence_length) {
    return PuDOccurrenceAdvance::Complete;
  }
  configure_pud_occurrence(req, spec);
  return PuDOccurrenceAdvance::Advanced;
}

PuDMovementTimingConstraints make_movement_timing_constraints(
    const DRAMSpec& spec) {
  return {{
      {Request::Type::LCMOV, 0, 1, spec.get_timing_value("nRCD")},
      {Request::Type::LCMOV, 1, 2, spec.get_timing_value("nRTP")},
      {Request::Type::LCMOV, 4, 5,
       spec.get_timing_value("nRELOC") + spec.get_timing_value("nWR")},
      {Request::Type::GBMOV, 0, 2, spec.get_timing_value("nRAS")},
      {Request::Type::GBMOV, 2, 3, spec.get_timing_value("nRELOC")},
      {Request::Type::GBMOV, 3, 4, spec.get_timing_value("nWR")},
  }};
}

bool check_pud_occurrence_timing(
    const Request& req, Clk_t clk,
    const PuDMovementTimingConstraints& constraints) {
  if (!is_movement_request_type(req.type_id)) {
    return true;
  }

  const size_t sequence_length = get_pud_sequence_length(req);
  if (req.occurrence_index >= sequence_length ||
      req.occurrence_issue_history.size() != sequence_length) {
    throw std::logic_error(fmt::format(
        "{} has inconsistent timing context: cursor {}, history {}, sequence {}",
        request_type_name(req.type_id), req.occurrence_index,
        req.occurrence_issue_history.size(), sequence_length));
  }

  for (const auto& constraint : constraints) {
    if (constraint.request_type != req.type_id ||
        constraint.following != req.occurrence_index) {
      continue;
    }

    const Clk_t predecessor_clk =
        req.occurrence_issue_history[constraint.predecessor];
    if (predecessor_clk == Request::kOccurrenceNotIssued) {
      throw std::logic_error(fmt::format(
          "{} occurrence {} timing predecessor {} has not issued",
          request_type_name(req.type_id), req.occurrence_index,
          constraint.predecessor));
    }

    return clk >= predecessor_clk + constraint.delay;
  }

  return true;
}

bool check_pud_local_timing(const Request& req, Clk_t clk, const DRAMSpec& spec) {
  if (!req.pud_locations || !is_pud_request_type(req.type_id)) {
    throw std::logic_error("Range timing requires a located PuD request");
  }
  const auto next = describe_pud_occurrence(req, req.occurrence_index, spec);
  const int bank = spec.get_level_id("Bank");
  // Repeated commands use only this invocation's issue history. Keeping the
  // declarative edges as the numeric authority also retains timing overrides.
  for (size_t i = 0; i < req.occurrence_index; ++i) {
    const auto previous = describe_pud_occurrence(req, i, spec);
    const auto issued = req.occurrence_issue_history.at(i);
    if (issued == Request::kOccurrenceNotIssued) {
      throw std::logic_error("Missing range timing predecessor");
    }
    for (const auto& edge : spec.timing_cons[bank][previous.command]) {
      if (edge.cmd == next.command && !edge.sibling && clk < issued + edge.val) {
        return false;
      }
    }
  }
  return true;
}

const char* pud_occurrence_role_name(PuDOccurrenceRole role) {
  switch (role) {
    case PuDOccurrenceRole::Operand:
      return "operand";
    case PuDOccurrenceRole::Source:
      return "source";
    case PuDOccurrenceRole::Destination:
      return "destination";
  }
  throw std::logic_error("Unknown PuD occurrence role");
}

}  // namespace Ramulator
