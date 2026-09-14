#include <algorithm>
#include <charconv>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include "ramulator/base/param.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/pud_request_routing.h"

namespace Ramulator {

// Finite physical Request stream. No macro semantics or payload values.
class PuDTrace : public IFrontEnd, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd, PuDTrace, "PuDTrace")

  std::string m_path;
  std::vector<Request> m_requests;
  size_t m_next = 0;
  bool m_inflight = false;
  size_t s_submitted = 0, s_completed = 0, s_completed_occurrences = 0;

 public:
  void init() override {
    RAMULATOR_PARSE_PARAM(m_clock_ratio, unsigned int, "clock_ratio").required();
    RAMULATOR_PARSE_PARAM(m_path, std::string, "path").required();
    m_stats.add("physical_requests_submitted", s_submitted);
    m_stats.add("physical_requests_completed", s_completed);
    m_stats.add("physical_command_occurrences_completed", s_completed_occurrences);
  }

  void setup(IFrontEnd*, IMemorySystem* memory) override {
    auto resolver = memory->location_resolver();
    if (!resolver) throw std::runtime_error("PuDTrace requires an installed location resolver");
    std::ifstream input(m_path);
    if (!input) throw std::runtime_error("Cannot open PuDTrace: " + m_path);
    std::string line;
    size_t line_number = 0;
    auto read_line = [&]() {
      if (!std::getline(input, line)) throw std::runtime_error("Incomplete PuDTrace header");
      ++line_number;
      if (!line.empty() && line.back() == '\r') line.pop_back();
    };
    read_line();
    if (line != "PUD_TRACE 1") throw std::runtime_error("Expected PUD_TRACE 1");
    read_line();
    if (line != "PROFILE " + resolver->association().profile.name)
      throw std::runtime_error("PuDTrace placement profile mismatch");
    read_line();
    if (line != "RANKS " + std::to_string(resolver->association().ranks))
      throw std::runtime_error("PuDTrace rank context mismatch");

    const std::unordered_map<std::string, int> types = {
        {"RowCopy", Request::Type::RowCopy}, {"MAJ3", Request::Type::MAJ3},
        {"MAJ5", Request::Type::MAJ5}, {"NOT", Request::Type::NOT},
        {"NOT_COPY", Request::Type::NOT_COPY}, {"LC-MOV", Request::Type::LCMOV},
        {"GB-MOV", Request::Type::GBMOV}};
    while (std::getline(input, line)) {
      ++line_number;
      try {
        std::istringstream fields(line);
        std::string opcode;
        fields >> opcode;
        auto type = types.find(opcode);
        if (type == types.end()) throw std::runtime_error("unknown physical opcode");
        std::vector<int> values;
        std::string token;
        while (fields >> token) {
          int value;
          const auto parsed = std::from_chars(token.data(), token.data() + token.size(), value);
          if (parsed.ec != std::errc{} || parsed.ptr != token.data() + token.size())
            throw std::runtime_error("expected an in-range integer");
          values.push_back(value);
        }
        if (values.size() < 7)
          throw std::runtime_error("expected integer context, mat endpoints and operands");
        const int first = values[4], last = values[5];
        auto row = [&](int id) {
          return PuD::ExternalRow{values[0], values[1], values[2], values[3], id};
        };
        std::vector<PuD::PairedOperand> operands;
        if (is_movement_request_type(type->second)) {
          if (values.size() != 10) throw std::runtime_error("movement requires two row/group operands");
          const PuD::MatRange src = type->second == Request::Type::GBMOV
                                      ? PuD::MatRange{first, first} : PuD::MatRange{first, last};
          const PuD::MatRange dst = type->second == Request::Type::GBMOV
                                      ? PuD::MatRange{last, last} : src;
          operands.push_back(resolver->pair(resolver->group_footprint(
              row(values[6]), src, PuD::Group{values[7]})));
          operands.push_back(resolver->pair(resolver->group_footprint(
              row(values[8]), dst, PuD::Group{values[9]})));
        } else {
          for (size_t i = 6; i < values.size(); ++i)
            operands.push_back(resolver->pair(
                resolver->compute_footprint(row(values[i]), PuD::MatRange{first, last})));
        }
        Request request(resolver, std::move(operands), type->second);
        validate_pud_operand_count(request);
        request.size_bytes = is_movement_request_type(request.type_id)
                                 ? Request::kMovementSizeBytesNotApplicable : memory->get_tx_bytes();
        request.source_id = 0;
        request.callback = [this](Request& completed) {
          ++s_completed;
          s_completed_occurrences += std::count_if(
              completed.occurrence_issue_history.begin(), completed.occurrence_issue_history.end(),
              [](Clk_t clock) { return clock != Request::kOccurrenceNotIssued; });
          m_inflight = false;
        };
        m_requests.push_back(std::move(request));
      } catch (const std::exception& error) {
        throw std::runtime_error("PuDTrace line " + std::to_string(line_number) + ": " + error.what());
      }
    }
  }

  void tick() override {
    if (m_inflight || m_next == m_requests.size()) return;
    // Keep the same canonical Request on backpressure. One outstanding request
    // serializes all dependencies through the existing recovery callback.
    m_inflight = true;
    if (m_memory_system->send(m_requests[m_next])) {
      ++m_next;
      ++s_submitted;
    } else {
      m_inflight = false;
    }
  }

  bool is_finished() override {
    return m_next == m_requests.size() && !m_inflight;
  }
};

}  // namespace Ramulator
