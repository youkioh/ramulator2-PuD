#include "ramulator/base/request.h"

namespace Ramulator {

Request::Request(Addr_t addr, int type) : addr(addr), type_id(type){};

Request::Request(AddrVec_t addr_vec, int type) : addr_vec(std::move(addr_vec)), type_id(type){};

Request::Request(std::vector<AddrVec_t> operands, int type)
    : type_id(type), operands(std::move(operands)){};

Request::Request(Addr_t addr, int type, int source_id, std::function<void(Request&)> callback)
    : addr(addr), type_id(type), source_id(source_id), callback(callback){};

Request::Request(AddrVec_t addr_vec, Cmd_t, int final_cmd) : addr_vec(std::move(addr_vec)), final_command(final_cmd){};

bool is_pud_request_type(int type_id) {
  return type_id >= Request::Type::RowCopy && type_id <= Request::Type::NOT;
}

const char* request_type_name(int type_id) {
  switch (type_id) {
    case Request::Type::Read: return "Read";
    case Request::Type::Write: return "Write";
    case Request::Type::RowCopy: return "RowCopy";
    case Request::Type::MAJ3: return "MAJ3";
    case Request::Type::MAJ5: return "MAJ5";
    case Request::Type::NOT: return "NOT";
    default: return "Unknown";
  }
}

}  // namespace Ramulator
