#include "ramulator/base/pud_functional.h"

#include <iostream>
#include <stdexcept>
#include <string>

using namespace Ramulator;

namespace {

bool verbose = false;
std::string context;

AddrVec_t address(int row, int column = 0) {
  return {0, 0, 0, 0, row, column};
}

Request request(int type, std::initializer_list<int> rows) {
  std::vector<AddrVec_t> operands;
  for (int row : rows) {
    operands.push_back(address(row));
  }
  return Request(operands, type);
}

void check(bool condition, const char* message) {
  if (verbose) {
    std::cout << context << " " << message << ": actual=" << condition << " expected=1\n";
  }
  if (!condition) {
    throw std::runtime_error(message);
  }
}

void check_value(unsigned actual, unsigned expected, const std::string& label) {
  if (verbose || actual != expected) {
    std::cout << context << " " << label << ": actual=" << actual << " expected=" << expected << '\n';
  }
  if (actual != expected) {
    throw std::runtime_error(context + " " + label);
  }
}

void check_row(const FunctionalRow& actual, const FunctionalRow& expected, const std::string& label) {
  check_value(actual.size(), expected.size(), label + " width");
  for (size_t lane = 0; lane < actual.size(); ++lane) {
    check_value(actual[lane], expected[lane], label + " lane=" + std::to_string(lane));
  }
}

template <typename F>
void rejects(F action) {
  bool rejected = false;
  try {
    action();
  } catch (const std::exception&) {
    rejected = true;
  }
  check(rejected, "Expected invalid input to be rejected");
}

void test_rowcopy() {
  PuDFunctionalSimulator sim(4);
  const FunctionalRow source{0, 1, 1, 0};
  sim.write_row(address(0), source);
  sim.write_row(address(1), {1, 0, 0, 1});
  sim.execute(request(Request::Type::RowCopy, {0, 1}));
  check_row(sim.read_row(address(1)), source, "Single-destination RowCopy row=1");
  auto req = request(Request::Type::RowCopy, {0, 2, 3});
  req.operands[0][5] = 17;
  req.arrive = 42;
  req.command = 123;
  req.occurrence_issue_history = {7, 8};
  req.callback = [](Request&) { throw std::runtime_error("Callback must not run"); };
  const auto operands = req.operands;
  sim.execute(req);
  for (int row : {0, 1, 2, 3}) {
    check_row(sim.read_row(address(row)), source, "RowCopy row=" + std::to_string(row));
  }
  check(req.operands == operands && req.arrive == 42 && req.command == 123 &&
            req.occurrence_issue_history == std::vector<Clk_t>({7, 8}),
        "Request must remain unchanged");
}

void test_majority(int count, int type) {
  const size_t lanes = 1u << count;
  PuDFunctionalSimulator sim(lanes);
  std::vector<AddrVec_t> operands;
  for (int bit = 0; bit < count; ++bit) {
    FunctionalRow plane(lanes);
    for (size_t lane = 0; lane < lanes; ++lane) {
      plane[lane] = (lane >> bit) & 1;
    }
    operands.push_back(address(bit));
    sim.write_row(operands.back(), plane);
  }
  sim.execute(Request(operands, type));
  for (size_t lane = 0; lane < lanes; ++lane) {
    int ones = 0;
    for (int bit = 0; bit < count; ++bit) {
      ones += (lane >> bit) & 1;
    }
    for (const auto& operand : operands) {
      check_value(sim.read_row(operand)[lane], ones > count / 2,
                  "row=" + std::to_string(operand[4]) + " lane=" + std::to_string(lane));
    }
  }
}

void test_not() {
  PuDFunctionalSimulator sim(4);
  sim.write_row(address(0), {0, 1, 1, 0});
  sim.execute(request(Request::Type::NOT, {0}));
  check_row(sim.read_row(address(0)), {1, 0, 0, 1}, "In-place NOT row=0");
}

void test_not_copy() {
  PuDFunctionalSimulator sim(4);
  sim.write_row(address(0), {0, 1, 1, 0});
  sim.execute(request(Request::Type::NOT_COPY, {0, 1}));
  for (int row : {0, 1}) {
    check_row(sim.read_row(address(row)), {1, 0, 0, 1}, "NOT_COPY row=" + std::to_string(row));
  }
}

void test_validation() {
  rejects([] { PuDFunctionalSimulator sim(0); });
  PuDFunctionalSimulator sim(4);
  const FunctionalRow source{0, 1, 0, 1};
  sim.write_row(address(0), source);
  rejects([&] { sim.read_row(address(1)); });
  rejects([&] { sim.write_row(address(1), {0}); });
  rejects([&] { sim.write_row(address(1), {0, 1, 2, 0}); });
  rejects([&] { sim.write_row({0}, source); });
  for (int type : {Request::Type::Read, Request::Type::Write, Request::Type::LCMOV, Request::Type::GBMOV}) {
    rejects([&] { sim.execute(request(type, {0, 1})); });
  }
  rejects([&] { sim.execute(request(-1, {0})); });
  for (int type : {Request::Type::RowCopy, Request::Type::MAJ3, Request::Type::MAJ5, Request::Type::NOT,
                   Request::Type::NOT_COPY}) {
    rejects([&] { sim.execute(request(type, {})); });
  }
  rejects([&] { sim.execute(request(Request::Type::MAJ3, {0, 1, 2})); });
  auto malformed = request(Request::Type::RowCopy, {0, 1, 2});
  malformed.operands.back() = {0};
  rejects([&] { sim.execute(malformed); });
  rejects([&] { sim.read_row(address(1)); });
  check_row(sim.read_row(address(0)), source, "Rejected request input row=0");
  check_row(sim.read_row(address(0, 1023)), source, "Column-independent row=0");
  auto other_bank = address(0);
  other_bank[3] = 1;
  rejects([&] { sim.read_row(other_bank); });
}

// Test-only bitslice helpers; no operation generator or layout framework.
FunctionalRow plane(const std::vector<unsigned>& values, unsigned bit) {
  FunctionalRow result;
  for (unsigned value : values) {
    result.push_back((value >> bit) & 1);
  }
  return result;
}

void test_prada_table2_add() {
  enum { A1, A0, B1, B0, R2, R1, R0, V, W, X, Y, Z, Zero };
  std::vector<unsigned> a, b;
  for (unsigned lhs = 0; lhs < 4; ++lhs) {
    for (unsigned rhs = 0; rhs < 4; ++rhs) {
      a.push_back(lhs);
      b.push_back(rhs);
    }
  }
  PuDFunctionalSimulator sim(a.size());
  sim.write_row(address(A0), plane(a, 0));
  sim.write_row(address(A1), plane(a, 1));
  sim.write_row(address(B0), plane(b, 0));
  sim.write_row(address(B1), plane(b, 1));
  sim.write_row(address(Zero), FunctionalRow(a.size(), 0));
  // PRADA Table 2: exact 11-step order supplied for this test. The paper's
  // numbering typo does not change execution order. Every scratch/result row
  // is initialized by an earlier request before it is read.
  const std::vector<Request> sequence{
      request(Request::Type::RowCopy, {Zero, R2, R1, R0}),
      request(Request::Type::RowCopy, {A0, V, Y}),
      request(Request::Type::RowCopy, {B0, W, Z}),
      request(Request::Type::MAJ3, {R2, V, W}),
      request(Request::Type::NOT_COPY, {W, X}),
      request(Request::Type::MAJ5, {R0, W, X, Y, Z}),
      request(Request::Type::RowCopy, {A1, W, Y}),
      request(Request::Type::RowCopy, {B1, X, Z}),
      request(Request::Type::MAJ3, {R2, Y, Z}),
      request(Request::Type::NOT_COPY, {Y, R1}),
      request(Request::Type::MAJ5, {R1, V, W, X, Y}),
  };
  const char* row_names[] = {"A1", "A0", "B1", "B0", "R2", "R1", "R0", "V", "W", "X", "Y", "Z", "0"};
  auto verify = [&](std::initializer_list<int> rows, auto oracle) {
    for (int row : rows) {
      for (size_t lane = 0; lane < a.size(); ++lane) {
        check_value(sim.read_row(address(row))[lane], oracle(a[lane], b[lane]),
                    std::string(row_names[row]) + " lane=" + std::to_string(lane) + " a=" + std::to_string(a[lane]) +
                        " b=" + std::to_string(b[lane]));
      }
    }
  };
  for (size_t step = 0; step < sequence.size(); ++step) {
    context = "PRADA step=" + std::to_string(step + 1) + " " + request_type_name(sequence[step].type_id);
    sim.execute(sequence[step]);
    if (step == 3) {
      verify({R2, V, W}, [](unsigned a, unsigned b) { return ((a & 1) + (b & 1)) >> 1; });
    }
    if (step == 4) {
      verify({W, X}, [](unsigned a, unsigned b) { return 1 ^ (((a & 1) + (b & 1)) >> 1); });
    }
    if (step == 5) {
      verify({R0, W, X, Y, Z}, [](unsigned a, unsigned b) { return (a + b) & 1; });
    }
    if (step == 8) {
      verify({R2, Y, Z}, [](unsigned a, unsigned b) { return (a + b) >> 2; });
    }
    if (step == 9) {
      verify({Y, R1}, [](unsigned a, unsigned b) { return 1 ^ ((a + b) >> 2); });
    }
    if (step == 10) {
      verify({R1, V, W, X, Y}, [](unsigned a, unsigned b) { return ((a + b) >> 1) & 1; });
    }
  }
  for (size_t lane = 0; lane < a.size(); ++lane) {
    unsigned decoded = sim.read_row(address(R0))[lane] | (sim.read_row(address(R1))[lane] << 1) |
                       (sim.read_row(address(R2))[lane] << 2);
    check_value(decoded, a[lane] + b[lane],
                "decoded R2R1R0 lane=" + std::to_string(lane) + " a=" + std::to_string(a[lane]) +
                    " b=" + std::to_string(b[lane]));
  }
  context = "PRADA source preservation";
  check_row(sim.read_row(address(A0)), plane(a, 0), "A0");
  check_row(sim.read_row(address(A1)), plane(a, 1), "A1");
  check_row(sim.read_row(address(B0)), plane(b, 0), "B0");
  check_row(sim.read_row(address(B1)), plane(b, 1), "B1");
  check_row(sim.read_row(address(Zero)), FunctionalRow(a.size(), 0), "0");
  // Exercise the ordered-stream overload on the same logical sequence.
  context = "PRADA batch final";
  sim.execute(sequence);
  verify({R0}, [](unsigned a, unsigned b) { return (a + b) & 1; });
  verify({R1}, [](unsigned a, unsigned b) { return ((a + b) >> 1) & 1; });
  verify({R2}, [](unsigned a, unsigned b) { return (a + b) >> 2; });
}

}  // namespace

int main(int argc, char* argv[]) {
  for (int i = 1; i < argc; ++i) {
    const std::string option = argv[i];
    if (option == "-v" || option == "--verbose") {
      verbose = true;
    } else {
      std::cerr << "Usage: " << argv[0] << " [-v|--verbose]\n";
      return 2;
    }
  }
  try {
    context = "RowCopy";
    test_rowcopy();
    context = "MAJ3";
    test_majority(3, Request::Type::MAJ3);
    context = "MAJ5";
    test_majority(5, Request::Type::MAJ5);
    context = "NOT";
    test_not();
    context = "NOT_COPY";
    test_not_copy();
    context = "validation";
    test_validation();
    test_prada_table2_add();
    std::cout << "PASS: five primitives (exhaustive MAJ3/MAJ5), validation, PRADA Table 2 ADD (16 input pairs)\n";
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n';
    return 1;
  }
}
