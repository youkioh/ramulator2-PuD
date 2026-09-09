#ifndef RAMULATOR_EXAMPLES_PUD_V2_MICROBENCHMARK_H
#define RAMULATOR_EXAMPLES_PUD_V2_MICROBENCHMARK_H

#include <algorithm>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/base/config_node.h"
#include "ramulator/dram/pud_location.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"

// Controlled streams use unique, valid source IDs with the existing trace schema.
// Results retain the completed Request's immutable locations, never a range copy
// or a second execution cursor.
namespace PuDV2Benchmark {
using namespace Ramulator;

inline void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error("v2 benchmark: " + message);
}

struct Result {
  std::string label;
  int type;
  Clk_t local_anchor;
  Clk_t arrive = -1, depart = -1;
  std::shared_ptr<const PuD::RequestLocations> locations;
};
struct Command {
  Clk_t clk;
  std::string name;
};

inline int run(const ConfigNode& config, const std::string& trace_path, bool movement) {
  std::unique_ptr<IFrontEnd> frontend(Factory::create_frontend(config));
  std::unique_ptr<IMemorySystem> memory(Factory::create_memory_system(config));
  frontend->connect_memory_system(memory.get());
  memory->connect_frontend(frontend.get());
  const auto resolver = memory->location_resolver();
  require(bool(resolver), "select a v2 profile in the exported configuration");
  const auto controller = config["memory_system"]["controllers"].seq().front();
  require(controller["refresh_manager"]["impl"].as<std::string>() == "NoRefresh",
          "isolated/overlap anchor scenarios require NoRefresh");
  const int engines = controller["pud_compute_engines"].as<int>(8);
  std::cout << "profile=" << resolver->association().profile.name << " E=" << engines
            << "\ntransport=T-A resolved-target consumption at ACT issue\n"
               "Transport latency, mat-queue stalls and target-delivery C/A contention "
               "are omitted, not physically zero.\n";

  std::vector<Result> results;
  Clk_t clk = 0;
  auto tick = [&] {
    require(clk < 20000, "stream did not drain within 20000 CK");
    ++clk;
    memory->tick();
  };
  auto make = [&](int type, PuD::MatRange mats, int count, int first_row = 100) {
    std::vector<PuD::PairedOperand> operands;
    for (int i = 0; i < count; ++i) {
      const PuD::ExternalRow row{0, 0, 0, 0, first_row+i};
      const auto selected = type == Request::Type::GBMOV ? PuD::MatRange{6+i, 6+i} : mats;
      auto region = is_movement_request_type(type)
          ? resolver->group_footprint(row, selected, PuD::Group{3+i})
          : resolver->compute_footprint(row, selected);
      operands.push_back(resolver->pair(std::move(region)));
    }
    Request req(resolver, std::move(operands), type);
    req.size_bytes = is_movement_request_type(type) ? Request::kMovementSizeBytesNotApplicable : memory->get_tx_bytes();
    return req;
  };
  auto submit = [&](Request req, const std::string& label, Clk_t anchor,
                    std::function<void()> callback = {}) {
    const int source = static_cast<int>(results.size());
    require(source < frontend->get_num_cores(), "source_id exceeds configured num_cores");
    results.push_back({label, req.type_id, anchor});
    req.source_id = source;
    req.callback = [&, source, callback](Request& done) {
      auto& result = results.at(source);
      require(result.depart < 0, "duplicate callback");
      result.arrive = done.arrive;
      result.depart = done.depart;
      result.locations = done.pud_locations;
      require(bool(result.locations), "completion lost paired locations");
      if (callback) callback();
    };
    while (!memory->send(req)) tick();
    return source;
  };
  auto wait = [&](int source) {
    while (results.at(source).depart < 0) tick();
  };

  // Retain only result identities for cross-request ordering checks.
  std::vector<std::pair<int, int>> overlap_pairs;
  std::vector<int> producers;
  int dependent = -1;
  if (movement) {
    for (auto mats : {PuD::MatRange{2, 2}, PuD::MatRange{15, 18}, PuD::MatRange{0, 127}}) {
      wait(submit(make(Request::Type::LCMOV, mats, 2), "isolated LC-MOV", 130));
    }
    wait(submit(make(Request::Type::GBMOV, {6, 6}, 2), "isolated GB-MOV", 75));
  } else {
    for (auto mats : {PuD::MatRange{2, 2}, PuD::MatRange{15, 16}, PuD::MatRange{0, 127}}) {
      for (auto [type, count, anchor] : std::vector<std::tuple<int, int, Clk_t>>{
               {Request::Type::RowCopy, 2, 61}, {Request::Type::MAJ3, 3, 66},
               {Request::Type::MAJ5, 5, 76}, {Request::Type::NOT, 1, 99},
               {Request::Type::NOT_COPY, 2, 104}}) {
        wait(submit(make(type, mats, count), "isolated", anchor));
      }
    }
    for (int destinations : {2, 5}) {
      wait(submit(make(Request::Type::RowCopy, {15, 16}, destinations+1),
                  "multi-destination", 40+5*destinations+16));
    }
    for (int second : {Request::Type::RowCopy, Request::Type::NOT_COPY}) {
      int a = submit(make(Request::Type::RowCopy, {15, 16}, 2), "independent A", 61);
      int b = submit(make(second, {17, 20}, 2), "independent B",
                     second == Request::Type::RowCopy ? 61 : 104);
      wait(a);
      wait(b);
      overlap_pairs.emplace_back(a, b);
    }
    // Consumer submission happens inside the last required producer callback.
    auto completed_producer = [&] {
      if (producers.size() == 2 &&
          std::all_of(producers.begin(), producers.end(), [&](int p) { return results[p].depart >= 0; })) {
        dependent = submit(make(Request::Type::NOT, {15, 20}, 1, 101), "callback-dependent", 99);
      }
    };
    producers.push_back(submit(make(Request::Type::RowCopy, {15, 16}, 2),
                               "producer A", 61, completed_producer));
    producers.push_back(submit(make(Request::Type::NOT_COPY, {17, 20}, 2),
                               "producer B", 104, completed_producer));
    wait(producers[0]);
    wait(producers[1]);
    require(dependent >= 0, "producer join did not submit the dependent primitive");
    wait(dependent);
  }

  frontend->finalize();
  memory->finalize();
  std::ifstream trace(trace_path);
  require(bool(trace), "cannot open command trace " + trace_path);
  std::map<int, std::vector<Command>> commands;
  std::string line;
  std::getline(trace, line);
  while (std::getline(trace, line)) {
    std::istringstream stream(line);
    std::vector<std::string> fields;
    std::string field;
    while (std::getline(stream, field, ',')) fields.push_back(field);
    require(fields.size() >= 4, "malformed trace");
    commands[std::stoi(fields.back())].push_back({std::stoll(fields.front()), fields[1]});
  }
  for (size_t source = 0; source < results.size(); ++source) {
    const auto& result = results[source];
    const auto& issued = commands.at(static_cast<int>(source));
    const Clk_t first = issued.front().clk;
    const Clk_t terminal = issued.back().clk;
    require(issued.front().name.starts_with("ACT_"), "first occurrence is not activation");
    require(issued.back().name == "PREpb", "terminal occurrence is not PREpb");
    require(result.depart-first == result.local_anchor, "local anchor shifted");
    require(result.depart-terminal == 16, "terminal recovery mismatch");
    std::cout << "source=" << source << " " << result.label << " " << request_type_name(result.type);
    for (const auto& operand : result.locations->operands) {
      const auto& origin = operand.location.origin;
      std::cout << " [bank=" << origin.bank << " subarray=" << origin.subarray
                << " row=" << origin.local_row << " mats=" << origin.mats.first << ".." << origin.mats.last;
      if (origin.group) std::cout << " group=" << origin.group->value;
      std::cout << ']';
    }
    std::cout << "\n  arrive=" << result.arrive << " first_ACT=" << first << " terminal_PRE=" << terminal
              << " recovery/depart=" << result.depart
              << " pre_ACT_wait=" << first-result.arrive
              << " local_anchor=" << result.local_anchor
              << " observed_execution=" << result.depart-first
              << " request_latency=" << result.depart-result.arrive << "\n  issued:";
    for (const auto& command : issued) std::cout << ' ' << command.name << '@' << command.clk;
    std::cout << '\n';
  }
  for (auto [a, b] : overlap_pairs) {
    const auto first_b = commands.at(b).front().clk;
    require(engines == 1 ? first_b >= results[a].depart : first_b < results[a].depart,
            "engine serialization/overlap mismatch");
    if (engines > 1) {
      require(commands.at(b)[1].clk < results[a].depart, "no later-occurrence overlap");
    }
  }
  if (dependent >= 0) {
    for (int producer : producers) {
      require(results[dependent].arrive >= results[producer].depart, "dependency submitted before recovery");
    }
  }
  memory->update_stats_recursive();
  const auto stats = memory->collect_stats();
  const auto ctrl_stats = stats["controller"];
  for (int type : {Request::Type::RowCopy, Request::Type::MAJ3, Request::Type::MAJ5,
                   Request::Type::NOT, Request::Type::NOT_COPY, Request::Type::LCMOV, Request::Type::GBMOV}) {
    const std::string name = is_movement_request_type(type) ? movement_statistic_name(type) : legacy_pud_statistic_name(type);
    int count = 0;
    Clk_t latency = 0;
    uint64_t moved_bits = 0;
    for (const auto& result : results) {
      if (result.type != type) continue;
      ++count;
      latency += result.depart-result.arrive;
      if (is_movement_request_type(type)) moved_bits += result.locations->operands.front().location.cell_count;
    }
    require(stats["total_num_pud_"+name+"_requests"].as<int>() == count, "system acceptance count");
    require(ctrl_stats["num_pud_"+name+"_reqs"].as<int>() == count, "controller acceptance count");
    require(ctrl_stats["num_pud_"+name+"_reqs_completed"].as<int>() == count, "completion count");
    require(ctrl_stats["pud_"+name+"_latency"].as<Clk_t>() == latency, "latency accounting");
    if (is_movement_request_type(type))
      require(ctrl_stats["pud_"+name+"_moved_bits"].as<uint64_t>() == moved_bits, "moved-bit accounting");
  }
  require(ctrl_stats["total_throughput_MBps"].as<double>() == 0.0, "PuD leaked into ordinary throughput");
  std::cout << "Validated public v2 substrate scenarios. Local totals already include terminal nRP.\n";
  return 0;
}
}  // namespace PuDV2Benchmark
#endif
