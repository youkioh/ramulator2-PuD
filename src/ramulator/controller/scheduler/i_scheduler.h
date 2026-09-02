#ifndef RAMULATOR_CONTROLLER_SCHEDULER_I_SCHEDULER_H
#define RAMULATOR_CONTROLLER_SCHEDULER_I_SCHEDULER_H

#include "ramulator/base/base.h"
#include "ramulator/base/function_ref.h"
#include "ramulator/controller/i_controller.h"

namespace Ramulator {

using RequestFilterRef = FunctionRef<bool(const Request&)>;

// Selects which pending request to issue next from the controller's queue.
class IScheduler {
  RAMULATOR_REGISTER_INTERFACE(IScheduler, "scheduler")
 public:
  // Contract:
  //   - eligibility_filter runs before prerequisite resolution. It must reason
  //     from the request's intended final_command and address.
  //   - The scheduler then derives req.command from req.final_command before
  //     invoking command_filter, so command-aware predicates retain the
  //     existing behavior.
  //   - Filters must not mutate controller state.
  virtual ReqBuffer::iterator get_best_request(
      ReqBuffer& buffer,
      RequestFilterRef eligibility_filter,
      RequestFilterRef command_filter) = 0;
};

}  // namespace Ramulator

#endif  // RAMULATOR_CONTROLLER_SCHEDULER_I_SCHEDULER_H
