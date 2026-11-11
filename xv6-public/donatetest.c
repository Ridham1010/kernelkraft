#include "types.h"
#include "user.h"
#include "sched_params.h"
#include "sched_api.h"

static void
forward(int in, int out)
{
  char buf[64];
  int n;

  while((n = read(in, buf, sizeof(buf))) > 0)
    if(write(out, buf, n) != n)
      break;
}

int
main(void)
{
  int p01[2], p12[2], p23[2];
  int p[4], i, n;
  char buf[64];

  pipe(p01);
  pipe(p12);
  pipe(p23);
  tracectl(3);
  p[0] = fork();
  if(p[0] == 0){
    close(p01[0]); close(p12[0]); close(p12[1]); close(p23[0]); close(p23[1]);
    for(i = 0; i < 16; i++){
      memset(buf, 'x', sizeof(buf));
      write(p01[1], buf, sizeof(buf));
    }
    close(p01[1]);
    exit();
  }
  p[3] = fork();
  if(p[3] == 0){
    close(p01[0]); close(p01[1]); close(p12[0]); close(p12[1]); close(p23[1]);
    // Only the final reader has a deadline. The earlier stages and the hog
    // have none, so they can only become urgent through donation.
    if(setworkflow(1, DONATION_TEST_DEADLINE) < 0){
      printf(1, "FAIL donatetest setworkflow\n");
      exit();
    }
    while(read(p23[0], buf, sizeof(buf)) > 0)
      ;
    close(p23[0]);
    exit();
  }
  p[2] = fork();
  if(p[2] == 0){
    close(p01[0]); close(p01[1]); close(p12[1]); close(p23[0]);
    forward(p12[0], p23[1]);
    close(p12[0]); close(p23[1]);
    exit();
  }
  p[1] = fork();
  if(p[1] == 0){
    close(p01[1]); close(p12[0]); close(p23[0]); close(p23[1]);
    forward(p01[0], p12[1]);
    close(p01[0]); close(p12[1]);
    exit();
  }
  n = fork();
  if(n == 0){
    close(p01[0]); close(p01[1]); close(p12[0]); close(p12[1]);
    close(p23[0]); close(p23[1]);
    for(i = 0; i < 10000000; i++)
      ;
    exit();
  }
  close(p01[0]); close(p01[1]); close(p12[0]); close(p12[1]);
  close(p23[0]); close(p23[1]);
  for(i = 0; i < 5; i++)
    wait();
  {
    struct sched_stats stats;
    schedinfo(&stats);
    printf(1, "CHECK donatetest donations=%d cycles=%d misses=%d\n",
           stats.donations, stats.cycles, stats.misses);
  }
  tracectl(4);
  write(1, "RESULT donatetest\n", 19);
  exit();
}
