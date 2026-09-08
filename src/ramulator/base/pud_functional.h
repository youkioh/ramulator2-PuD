#ifndef RAMULATOR_BASE_PUD_FUNCTIONAL_H
#define RAMULATOR_BASE_PUD_FUNCTIONAL_H

#include <cstdint>
#include <map>

#include "ramulator/base/request.h"

namespace Ramulator {

using FunctionalRow = std::vector<uint8_t>;

// Sparse whole-row values for DDR4_PuD's final device-visible operands:
// [Channel, Rank, BankGroup, Bank, Row, Column]. Column has no row-operation
// semantics. No device geometry, placement legality, timing, or state is modeled.
class PuDFunctionalSimulator {
 public:
  explicit PuDFunctionalSimulator(size_t row_width);

  // Explicit initialization or replacement; absent rows are never read as zero.
  void write_row(const AddrVec_t& address, const FunctionalRow& bits);
  const FunctionalRow& read_row(const AddrVec_t& address) const;

  void execute(const Request& request);
  void execute(const std::vector<Request>& requests);

 private:
  static AddrVec_t row_key(const AddrVec_t& address);
  size_t m_row_width;
  std::map<AddrVec_t, FunctionalRow> m_rows;
};

}  // namespace Ramulator

#endif  // RAMULATOR_BASE_PUD_FUNCTIONAL_H
