#include "ramulator/base/pud_functional.h"

#include <algorithm>
#include <stdexcept>

#include "ramulator/memory_system/pud_request_routing.h"

namespace Ramulator {

PuDFunctionalSimulator::PuDFunctionalSimulator(size_t row_width) : m_row_width(row_width) {
  if (row_width == 0) {
    throw std::invalid_argument("Functional row width must be positive");
  }
}

AddrVec_t PuDFunctionalSimulator::row_key(const AddrVec_t& address) {
  if (address.size() != 6 || std::any_of(address.begin(), address.end(), [](int v) { return v < 0; })) {
    throw std::invalid_argument("Functional row requires six nonnegative DDR4_PuD coordinates");
  }
  return AddrVec_t(address.begin(), address.end() - 1);
}

void PuDFunctionalSimulator::write_row(const AddrVec_t& address, const FunctionalRow& bits) {
  if (bits.size() != m_row_width || std::any_of(bits.begin(), bits.end(), [](uint8_t bit) { return bit > 1; })) {
    throw std::invalid_argument("Functional row must contain row_width binary lanes");
  }
  m_rows.insert_or_assign(row_key(address), bits);
}

const FunctionalRow& PuDFunctionalSimulator::read_row(const AddrVec_t& address) const {
  const auto it = m_rows.find(row_key(address));
  if (it == m_rows.end()) {
    throw std::runtime_error("Read of uninitialized functional row");
  }
  return it->second;
}

void PuDFunctionalSimulator::execute(const Request& request) {
  if (!is_inherited_pud_request_type(request.type_id)) {
    throw std::invalid_argument("Unsupported functional request (LC-MOV/GB-MOV interpretation is deferred)");
  }
  validate_pud_operand_count(request);
  // Validate every destination before any writes. Snapshot inputs so destructive
  // updates and repeated row operands always use the original lane values.
  for (const auto& operand : request.operands) {
    row_key(operand);
  }
  FunctionalRow result = read_row(request.operands.front());
  if (request.type_id == Request::Type::MAJ3 || request.type_id == Request::Type::MAJ5) {
    std::vector<FunctionalRow> inputs;
    for (const auto& operand : request.operands) {
      inputs.push_back(read_row(operand));
    }
    for (size_t lane = 0; lane < m_row_width; ++lane) {
      size_t ones = 0;
      for (const auto& input : inputs) {
        ones += input[lane];
      }
      result[lane] = ones > inputs.size() / 2;
    }
  } else if (request.type_id == Request::Type::NOT || request.type_id == Request::Type::NOT_COPY) {
    for (auto& bit : result) {
      bit ^= 1;
    }
  }
  const size_t first_destination = request.type_id == Request::Type::RowCopy ? 1 : 0;
  for (size_t i = first_destination; i < request.operands.size(); ++i) {
    write_row(request.operands[i], result);
  }
}

void PuDFunctionalSimulator::execute(const std::vector<Request>& requests) {
  for (const auto& request : requests) {
    execute(request);
  }
}

}  // namespace Ramulator
