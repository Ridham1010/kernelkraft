#include "types.h"
#include "stat.h"
#include "user.h"
#include "sched_params.h"
#include "sched_api.h"

int
main(int argc, char *argv[])
{
  struct sched_stats stats;
  
  if(schedinfo(&stats) < 0) {
    printf(1, "schedinfo failed\n");
    exit();
  }
  
  printf(1, "policy=%d ncpu=%d ticks=%d misses=%d donations=%d cycles=%d rejected=%d\n",
         stats.policy, stats.ncpu, stats.ticks, stats.misses,
         stats.donations, stats.cycles, stats.rejected);
  
  exit();
}
