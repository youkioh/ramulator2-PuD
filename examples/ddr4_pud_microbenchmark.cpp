#include <iostream>
#include <string>

#include "pud_microbenchmark.h"
#include "ramulator/base/config.h"

int main(int argc, char* argv[]) {
  try {
    const std::string config_path = argc > 1 ? argv[1] : "build/ddr4_pud_microbenchmark.yaml";
    const std::string trace_path = argc > 2 ? argv[2] : "build/ddr4_pud_trace.csv.ch0";
    const auto config = Ramulator::Config::parse_config_file(config_path);
    return PuDBenchmark::run(config, trace_path, PuDBenchmark::ScenarioSet::Unified);
  } catch (const std::exception& error) {
    std::cerr << "ddr4_pud_microbenchmark: " << error.what() << '\n';
    return 1;
  }
}
