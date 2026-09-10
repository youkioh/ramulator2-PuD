#include <iostream>
#include <string>

#include "pud_microbenchmark.h"
#include "ramulator/base/config.h"

int main(int argc, char* argv[]) {
  try {
    const std::string config_path = argc > 1 ? argv[1] : "build/mimdram_movement_microbenchmark.yaml";
    const std::string trace_prefix = argc > 2 ? argv[2] : "build/mimdram_movement_trace";
    const auto config = Ramulator::Config::parse_config_file(config_path);
    return PuDBenchmark::run(config, trace_prefix + ".ch0", PuDBenchmark::ScenarioSet::MovementOnly);
  } catch (const std::exception& error) {
    std::cerr << "mimdram_movement_microbenchmark: " << error.what() << '\n';
    return 1;
  }
}
