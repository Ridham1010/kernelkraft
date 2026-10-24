#include "types.h"
#include "stat.h"
#include "user.h"
#include "sched_params.h"

int
main(int argc, char *argv[])
{
  int policy = -1;
  
  if(argc != 2) {
    printf(1, "Usage: schedctl rr|edf|edf_donate\n");
    exit();
  }
  
  if(strcmp(argv[1], "rr") == 0) {
    policy = 0;
  } else if(strcmp(argv[1], "edf") == 0) {
    policy = 1;
  } else if(strcmp(argv[1], "edf_donate") == 0) {
    policy = 2;
  } else {
    printf(1, "Invalid policy: %s\n", argv[1]);
    printf(1, "Usage: schedctl rr|edf|edf_donate\n");
    exit();
  }
  
  if(setsched(policy) < 0) {
    printf(1, "setsched failed\n");
    exit();
  }
  
  printf(1, "Scheduler policy set to %s\n", argv[1]);
  exit();
}
