#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "ramulator/base/config.h"
#include "ramulator/base/config_node.h"
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"

namespace {

using Ramulator::AddrVec_t;
using Ramulator::Clk_t;
using Ramulator::ConfigNode;
using Ramulator::Request;

struct TraceCommand {
  Clk_t cycle;
  std::string command;
};

struct Scenario {
  std::string name;
  int type;
  int source_id;
  int first_mat;
  int second_mat;
  int hffs_per_mat;
  std::vector<std::string> expected_commands;
  std::vector<Clk_t> expected_normalized_cycles;
  Clk_t expected_recovery_latency;
};

struct Result {
  Scenario scenario;
  Clk_t arrive;
  Clk_t depart;
  std::vector<TraceCommand> commands;
  std::vector<Clk_t> normalized_cycles;
  unsigned long long moved_bits;
};

AddrVec_t address(int row, int column) {
  // Channel, Rank, BankGroup, Bank, Row, Column.
  return {0, 0, 0, 0, row, column};
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

std::vector<TraceCommand> read_commands(const std::string& trace_path, int type, int source_id) {
  std::ifstream trace(trace_path);
  if (!trace) {
    throw std::runtime_error("Could not open command trace " + trace_path);
  }

  std::vector<TraceCommand> commands;
  std::string line;
  std::getline(trace, line);  // Header.
  while (std::getline(trace, line)) {
    const auto fields = split_csv(line);
    if (fields.size() < 4) {
      throw std::runtime_error("Malformed command-trace record: " + line);
    }
    const int record_type = std::stoi(fields[fields.size() - 2]);
    const int record_source = std::stoi(fields.back());
    if (record_type == type && record_source == source_id) {
      commands.push_back({std::stoll(fields[0]), fields[1]});
    }
  }
  return commands;
}

ConfigNode configured_case(ConfigNode config, int hffs_per_mat, const std::string& trace_base) {
  auto memory_system = config["memory_system"];
  auto controllers = memory_system["controllers"];
  if (!memory_system.is_map() || !controllers.is_sequence()) {
    throw std::runtime_error("Benchmark config has no controller list");
  }

  ConfigNode configured_controllers(ConfigNode::Seq{});
  for (auto controller : controllers.seq()) {
    auto dram = controller["dram"];
    if (!dram.is_map()) {
      throw std::runtime_error("Benchmark controller has no DRAM config");
    }
    dram.set("hffs_per_mat", hffs_per_mat);
    controller.set("dram", std::move(dram));

    auto plugins = controller["controller_plugins"];
    if (!plugins.is_sequence()) {
      throw std::runtime_error("Benchmark requires CmdTraceRecorder");
    }
    bool recorder_found = false;
    ConfigNode configured_plugins(ConfigNode::Seq{});
    for (auto plugin : plugins.seq()) {
      if (plugin["impl"].as<std::string>("") == "CmdTraceRecorder") {
        plugin.set("path", trace_base);
        recorder_found = true;
      }
      configured_plugins.push_back(std::move(plugin));
    }
    if (!recorder_found) {
      throw std::runtime_error("Benchmark requires CmdTraceRecorder");
    }
    controller.set("controller_plugins", std::move(configured_plugins));
    configured_controllers.push_back(std::move(controller));
  }

  memory_system.set("controllers", std::move(configured_controllers));
  config.set("memory_system", std::move(memory_system));
  return config;
}

template <typename T>
T stat(const ConfigNode& controller_stats, const std::string& name) {
  const auto value = controller_stats[name];
  if (!value) {
    throw std::runtime_error("Missing controller statistic " + name);
  }
  return value.as<T>();
}

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

Result run_case(const ConfigNode& base_config, const Scenario& scenario, const std::string& trace_prefix) {
  const std::string trace_base = trace_prefix + "." + scenario.name;
  const std::string trace_path = trace_base + ".ch0";
  auto config = configured_case(base_config, scenario.hffs_per_mat, trace_base);

  std::unique_ptr<Ramulator::IFrontEnd> frontend(Ramulator::Factory::create_frontend(config));
  std::unique_ptr<Ramulator::IMemorySystem> memory_system(Ramulator::Factory::create_memory_system(config));
  frontend->connect_memory_system(memory_system.get());
  memory_system->connect_frontend(frontend.get());

  bool completed = false;
  Clk_t arrive = -1;
  Clk_t depart = -1;
  Request request({address(100, 3), address(101, 5)}, scenario.type);
  request.source_id = scenario.source_id;
  request.size_bytes = Request::kMovementSizeBytesNotApplicable;
  if (scenario.type == Request::Type::LCMOV) {
    request.movement = Request::LCMovementMetadata{{
        scenario.first_mat,
        scenario.second_mat,
    }};
  } else {
    request.movement = Request::GBMovementMetadata{
        scenario.first_mat,
        scenario.second_mat,
    };
  }
  request.callback = [&](Request& done) {
    arrive = done.arrive;
    depart = done.depart;
    completed = true;
  };

  while (!memory_system->send(request)) {
    memory_system->tick();
  }
  for (int ticks = 0; !completed && ticks < 512; ticks++) {
    memory_system->tick();
  }
  require(completed, scenario.name + " did not complete within 512 cycles");

  frontend->finalize();
  memory_system->finalize();
  const auto stats = memory_system->collect_stats();
  const auto controller_stats = stats["controller"];
  require(controller_stats.is_map(), "Benchmark could not find controller statistics");

  const std::string stat_name = scenario.type == Request::Type::LCMOV ? "lcmov" : "gbmov";
  require(stat<unsigned long long>(controller_stats, "num_pud_" + stat_name + "_reqs") == 1,
          scenario.name + " accepted-count mismatch");
  require(stat<unsigned long long>(controller_stats, "num_pud_" + stat_name + "_reqs_completed") == 1,
          scenario.name + " completion-count mismatch");
  require(stat<unsigned long long>(controller_stats, "num_read_reqs") == 0 &&
              stat<unsigned long long>(controller_stats, "num_write_reqs") == 0 &&
              stat<unsigned long long>(controller_stats, "num_read_reqs_served") == 0 &&
              stat<unsigned long long>(controller_stats, "num_write_reqs_served") == 0,
          scenario.name + " leaked into ordinary Read/Write counts");
  require(stat<double>(controller_stats, "read_throughput_MBps") == 0.0 &&
              stat<double>(controller_stats, "write_throughput_MBps") == 0.0 &&
              stat<double>(controller_stats, "total_throughput_MBps") == 0.0,
          scenario.name + " leaked into ordinary Read/Write throughput");

  auto commands = read_commands(trace_path, scenario.type, scenario.source_id);
  require(!commands.empty(), "No movement commands found for " + scenario.name);
  std::vector<Clk_t> normalized_cycles;
  normalized_cycles.reserve(commands.size());
  for (const auto& command : commands) {
    normalized_cycles.push_back(command.cycle - commands.front().cycle);
  }

  return {
      scenario,
      arrive,
      depart,
      std::move(commands),
      std::move(normalized_cycles),
      stat<unsigned long long>(controller_stats, "pud_" + stat_name + "_moved_bits"),
  };
}

void validate_case(const Result& result) {
  std::vector<std::string> observed_commands;
  observed_commands.reserve(result.commands.size());
  for (const auto& command : result.commands) {
    observed_commands.push_back(command.command);
  }

  const auto& scenario = result.scenario;
  require(observed_commands == scenario.expected_commands, scenario.name + " command sequence mismatch");
  require(result.normalized_cycles == scenario.expected_normalized_cycles,
          scenario.name + " normalized command-cycle mismatch");
  require(result.depart - result.commands.front().cycle == scenario.expected_recovery_latency,
          scenario.name + " terminal-recovery latency mismatch");
  require(result.depart - result.arrive ==
              (result.commands.front().cycle - result.arrive) + scenario.expected_recovery_latency,
          scenario.name + " request-latency decomposition mismatch");

  const auto selected_mat_count = scenario.type == Request::Type::LCMOV
                                      ? static_cast<unsigned long long>(scenario.second_mat - scenario.first_mat + 1)
                                      : 1ULL;
  require(result.moved_bits == selected_mat_count * static_cast<unsigned long long>(scenario.hffs_per_mat),
          scenario.name + " moved-bit count mismatch");
}

void print_result(const Result& result) {
  const auto first_act = result.commands.front().cycle;
  const auto terminal_pre = result.commands.back().cycle;
  const auto admission_offset = first_act - result.arrive;
  const auto modeled_latency = result.depart - first_act;
  const auto request_latency = result.depart - result.arrive;
  const auto terminal_recovery = result.depart - terminal_pre;

  std::cout << result.scenario.name << " (hffs_per_mat=" << result.scenario.hffs_per_mat << ")\n"
            << "  arrive=" << result.arrive << " first_ACT_MOV=" << first_act << " terminal_PREpb=" << terminal_pre
            << " depart=" << result.depart << '\n'
            << "  admission_offset=" << admission_offset << " request_latency=" << request_latency
            << " moved_bits=" << result.moved_bits << '\n'
            << "  expected_vs_observed_recovery=" << result.scenario.expected_recovery_latency << '/' << modeled_latency
            << " CK" << " terminal_PREpb_to_depart=" << terminal_recovery << " CK\n"
            << "  issued_commands:";
  for (const auto& command : result.commands) {
    std::cout << ' ' << command.command << '@' << command.cycle;
  }
  std::cout << "\n  normalized_issue_cycles:";
  for (size_t i = 0; i < result.commands.size(); i++) {
    std::cout << ' ' << result.commands[i].command << '@' << result.normalized_cycles[i];
  }
  std::cout << "\n";
}

}  // namespace

int main(int argc, char* argv[]) {
  try {
    const std::string config_path = argc > 1 ? argv[1] : "build/mimdram_movement_microbenchmark.yaml";
    const std::string trace_prefix = argc > 2 ? argv[2] : "build/mimdram_movement_trace";
    const auto config = Ramulator::Config::parse_config_file(config_path);

    const std::vector<std::string> lc_commands = {"ACT_MOV", "RD_MOV", "PREpb", "ACT_MOV", "WR_MOV", "PREpb"};
    const std::vector<Clk_t> lc_cycles = {0, 16, 39, 55, 94, 114};
    const std::vector<std::string> gb_commands = {"ACT_MOV", "ACT_MOV", "RD_MOV", "WR_MOV", "PREpb"};
    const std::vector<Clk_t> gb_cycles = {0, 1, 39, 41, 59};

    const std::vector<Scenario> scenarios = {
        {"lc_width1_h4", Request::Type::LCMOV, 200, 2, 2, 4, lc_commands, lc_cycles, 130},
        {"lc_width4_h4", Request::Type::LCMOV, 201, 2, 5, 4, lc_commands, lc_cycles, 130},
        {"gb_h4", Request::Type::GBMOV, 202, 6, 7, 4, gb_commands, gb_cycles, 75},
        {"lc_width1_h7", Request::Type::LCMOV, 203, 2, 2, 7, lc_commands, lc_cycles, 130},
        {"lc_width4_h7", Request::Type::LCMOV, 204, 2, 5, 7, lc_commands, lc_cycles, 130},
        {"gb_h7", Request::Type::GBMOV, 205, 6, 7, 7, gb_commands, gb_cycles, 75},
    };

    std::vector<Result> results;
    results.reserve(scenarios.size());
    for (const auto& scenario : scenarios) {
      results.push_back(run_case(config, scenario, trace_prefix));
      validate_case(results.back());
      print_result(results.back());
    }

    const auto same_timing = [](const Result& left, const Result& right) {
      return left.commands.size() == right.commands.size() && left.normalized_cycles == right.normalized_cycles &&
             left.depart - left.commands.front().cycle == right.depart - right.commands.front().cycle;
    };
    require(same_timing(results[0], results[1]), "LC range width changed command count or latency");
    require(same_timing(results[0], results[3]) && same_timing(results[1], results[4]) &&
                same_timing(results[2], results[5]),
            "hffs_per_mat changed movement latency");

    std::cout << "\nValidated: canonical LC/GB timelines and recovery; LC range width "
                 "and HFF width do not change latency; moved bits follow the accepted "
                 "LC/GB formulas; movement contributes zero ordinary Read/Write "
                 "throughput.\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "mimdram_movement_microbenchmark: " << error.what() << '\n';
    return 1;
  }
}
