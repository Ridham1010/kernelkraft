#include "types.h"
#include "stat.h"
#include "user.h"
#include "sched_params.h"

int
main(int argc, char *argv[])
{
  printf(1, "=== Negative Tests ===\n");
  
  // T-11: setsched(7) returns -1
  if (setsched(7) == -1) {
    printf(1, "T-11 PASS: setsched(7) = -1\n");
  } else {
    printf(1, "T-11 FAIL: setsched(7) returned %d\n", setsched(7));
  }
  
  // T-12a: setworkflow(1,0) returns -1 (deadline <= 0)
  if (setworkflow(1, 0) == -1) {
    printf(1, "T-12a PASS: setworkflow(1,0) = -1\n");
  } else {
    printf(1, "T-12a FAIL: setworkflow(1,0) returned %d\n", setworkflow(1, 0));
  }
  
  // T-12b: second setworkflow call returns -1
  // First call should succeed (workflow 2)
  if (setworkflow(2, 100) == 0) {
    printf(1, "T-12b first call: setworkflow(2,100) = 0 (OK)\n");
    // Second call should fail (already has workflow)
    if (setworkflow(2, 100) == -1) {
      printf(1, "T-12b PASS: second setworkflow call = -1\n");
    } else {
      printf(1, "T-12b FAIL: second call returned %d\n", setworkflow(2, 100));
    }
  } else {
    printf(1, "T-12b FAIL: first call returned %d\n", setworkflow(2, 100));
  }
  
  exit();
}
