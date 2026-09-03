#include "ramulator/base/request.h"

namespace Ramulator {

Request::Request(Addr_t addr, int type) : addr(addr), type_id(type){};

Request::Request(AddrVec_t addr_vec, int type) : addr_vec(std::move(addr_vec)), type_id(type){};

Request::Request(std::vector<AddrVec_t> operands, int type)
    : type_id(type), operands(std::move(operands)){};

Request::Request(Addr_t addr, int type, int source_id, std::function<void(Request&)> callback)
    : addr(addr), type_id(type), source_id(source_id), callback(callback){};

Request::Request(AddrVec_t addr_vec, Cmd_t, int final_cmd) : addr_vec(std::move(addr_vec)), final_command(final_cmd){};

bool is_inherited_pud_request_type(int type_id) {
  switch (type_id) {
    case Request::Type::RowCopy:
    case Request::Type::MAJ3:
    case Request::Type::MAJ5:
    case Request::Type::NOT: return true;
    default: return false;
  }
}

bool is_movement_request_type(int type_id) {
  return type_id == Request::Type::LCMOV || type_id == Request::Type::GBMOV;
}

bool is_pud_request_type(int type_id) {
  return is_inherited_pud_request_type(type_id) || is_movement_request_type(type_id);
}

bool is_controller_sequenced_request_type(int type_id) {
  return is_pud_request_type(type_id);
}

std::optional<size_t> legacy_pud_statistic_slot(int type_id) {
  switch (type_id) {
    case Request::Type::RowCopy: return 0;
    case Request::Type::MAJ3: return 1;
    case Request::Type::MAJ5: return 2;
    case Request::Type::NOT: return 3;
    default: return std::nullopt;
  }
}

const char* legacy_pud_statistic_name(int type_id) {
  switch (type_id) {
    case Request::Type::RowCopy: return "rowcopy";
    case Request::Type::MAJ3: return "maj3";
    case Request::Type::MAJ5: return "maj5";
    case Request::Type::NOT: return "not";
    default: return nullptr;
  }
}

const char* request_type_name(int type_id) {
  switch (type_id) {
    case Request::Type::Read: return "Read";
    case Request::Type::Write: return "Write";
    case Request::Type::RowCopy: return "RowCopy";
    case Request::Type::MAJ3: return "MAJ3";
    case Request::Type::MAJ5: return "MAJ5";
    case Request::Type::NOT: return "NOT";
    case Request::Type::LCMOV: return "LC-MOV";
    case Request::Type::GBMOV: return "GB-MOV";
    default: return "Unknown";
  }
}

}  // namespace Ramulator
