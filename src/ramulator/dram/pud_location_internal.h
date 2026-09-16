#ifndef RAMULATOR_DRAM_PUD_LOCATION_INTERNAL_H
#define RAMULATOR_DRAM_PUD_LOCATION_INTERNAL_H

#include <cstdint>
#include <initializer_list>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace Ramulator::PuD::LocationDetail {
inline void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::invalid_argument("PuD location: " + message);
  }
}
inline void bound(int64_t value, int64_t size, const char* name) {
  require(value >= 0 && value < size, std::string(name) + " out of bounds");
}
inline int64_t product(std::initializer_list<int64_t> dimensions) {
  int64_t result = 1;
  for (int64_t dimension : dimensions) {
    require(dimension > 0, "dimensions must be positive");
    require(result <= std::numeric_limits<int64_t>::max() / dimension, "capacity overflow");
    result *= dimension;
  }
  return result;
}
inline std::vector<int> inverse_permutation(const std::vector<int>& forward, int64_t size) {
  require(static_cast<int64_t>(forward.size()) == size, "placement table size mismatch");
  std::vector<int> inverse(forward.size(), -1);
  for (size_t i = 0; i < forward.size(); ++i) {
    bound(forward[i], size, "placement table entry");
    require(inverse[forward[i]] == -1, "placement table must be a permutation");
    inverse[forward[i]] = static_cast<int>(i);
  }
  return inverse;
}

}  // namespace Ramulator::PuD::LocationDetail
#endif
