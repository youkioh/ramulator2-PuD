#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "ramulator/base/config.h"
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"

namespace {

using Ramulator::AddrVec_t;
using Ramulator::Clk_t;
using Ramulator::Request;

struct Workload {
  std::string name;
  int type;
  int source_id;
  std::vector<AddrVec_t> operands;
  Clk_t expected_isolated_latency;
};

struct Completion {
  std::string name;
  int source_id;
  Clk_t arrive;
  Clk_t depart;
  Clk_t expected_isolated_latency;
};

AddrVec_t address(int row) {
  // Channel, Rank, BankGroup, Bank, Row, Column.
  return {0, 0, 0, 0, row, 0};
}

std::vector<std::string> split_csv(const std::string& line) {
  std::vector<std::string> fields;
  std::istringstream stream(line);
  std::string field;
  while (std::getline(stream, field, ',')) {
    fields.push_back(field);
  }
  return fields;
}

std::map<int, Clk_t> read_first_issue_cycles(const std::string& trace_path) {
  std::ifstream trace(trace_path);
  if (!trace) {
    throw std::runtime_error("Could not open command trace " + trace_path);
  }

  std::map<int, Clk_t> first_issue;
  std::string line;
  std::getline(trace, line);  // Header.
  while (std::getline(trace, line)) {
    const auto fields = split_csv(line);
    if (fields.size() < 4) {
      throw std::runtime_error("Malformed command-trace record: " + line);
    }
    const int type = std::stoi(fields[fields.size() - 2]);
    const int source_id = std::stoi(fields.back());
    if (Ramulator::is_pud_request_type(type) && !first_issue.contains(source_id)) {
      first_issue[source_id] = std::stoll(fields[0]);
    }
  }
  return first_issue;
}

}  // namespace

int main(int argc, char* argv[]) {
  try {
    const std::string config_path = argc > 1 ? argv[1] : "build/ddr4_pud_microbenchmark.yaml";
    const std::string trace_path = argc > 2 ? argv[2] : "build/ddr4_pud_trace.csv.ch0";

    auto config = Ramulator::Config::parse_config_file(config_path);
    std::unique_ptr<Ramulator::IFrontEnd> frontend(Ramulator::Factory::create_frontend(config));
    std::unique_ptr<Ramulator::IMemorySystem> memory_system(Ramulator::Factory::create_memory_system(config));
    frontend->connect_memory_system(memory_system.get());
    memory_system->connect_frontend(frontend.get());

    const std::vector<Workload> workloads = {
        {"RowCopy (2 destinations)", Request::Type::RowCopy, 100, {address(100), address(101), address(102)}, 66},
        {"TRA (MAJ3 request)", Request::Type::MAJ3, 101, {address(110), address(111), address(112)}, 66},
        {"5RA (MAJ5 request)",
         Request::Type::MAJ5,
         102,
         {address(120), address(121), address(122), address(123), address(124)},
         76},
        {"NOT", Request::Type::NOT, 103, {address(130)}, 99},
    };

    std::vector<Completion> completions;
    for (const auto& workload : workloads) {
      bool completed = false;
      Request request(workload.operands, workload.type);
      request.source_id = workload.source_id;
      request.size_bytes = memory_system->get_tx_bytes();
      request.callback = [&](Request& done) {
        completions.push_back({
            workload.name,
            done.source_id,
            done.arrive,
            done.depart,
            workload.expected_isolated_latency,
        });
        completed = true;
      };

      // A rejected request retains its operand vector and is retried after a tick.
      while (!memory_system->send(request)) {
        memory_system->tick();
      }
      while (!completed) {
        memory_system->tick();
      }
    }

    frontend->finalize();
    memory_system->finalize();  // Also closes the command-trace file.
    const auto first_issue = read_first_issue_cycles(trace_path);

    std::cout << "primitive,source,arrive,first_issue,depart,pre_start,isolated,end_to_end\n";
    bool latency_mismatch = false;
    for (const auto& completion : completions) {
      const auto issue = first_issue.find(completion.source_id);
      if (issue == first_issue.end()) {
        throw std::runtime_error("No PuD command-trace record for source " + std::to_string(completion.source_id));
      }
      const Clk_t pre_start = issue->second - completion.arrive;
      const Clk_t isolated = completion.depart - issue->second;
      const Clk_t end_to_end = completion.depart - completion.arrive;
      std::cout << completion.name << ',' << completion.source_id << ',' << completion.arrive << ',' << issue->second
                << ',' << completion.depart << ',' << pre_start << ',' << isolated << ',' << end_to_end << '\n';
      latency_mismatch |= isolated != completion.expected_isolated_latency;
    }

    std::cout << "\nStatistics\n";
    memory_system->print_stats(std::cout);

    if (latency_mismatch) {
      std::cerr << "An isolated latency did not match the DDR4_2400R model.\n";
      return 1;
    }
    std::cout << "All isolated DDR4_2400R latency checks passed.\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "ddr4_pud_microbenchmark: " << error.what() << '\n';
    return 1;
  }
}
