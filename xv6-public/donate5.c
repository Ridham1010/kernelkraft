#include "types.h"
#include "user.h"
#include "sched_params.h"
#include "sched_api.h"

// 5-stage chain with an unrelated CPU hog.
//
//   stage0 -> p[0] -> stage1 -> p[1] -> stage2 -> p[2] -> stage3 -> p[3] -> stage4
//
// Only stage4 (the final reader) joins a workflow. Stages 0-3 and the hog
// have no deadline, so under plain EDF they are equal to the hog; under
// EDF with donation stage4's deadline flows back through all four pipes.

static void
copy_pipe(int in, int out)
{
  char b[64];
  int n;
  while((n = read(in, b, sizeof(b))) > 0)
    write(out, b, n);
}

int
main(void)
{
  int p[4][2], pid[5], hog, i, j, start;
  char b[64];

  for(i = 0; i < 4; i++)
    pipe(p[i]);
  tracectl(3);

  // The hog starts first, holds no pipe end and has no workflow.
  hog = fork();
  if(hog == 0){
    for(i = 0; i < 4; i++){ close(p[i][0]); close(p[i][1]); }
    for(;;)
      ;
  }

  start = uptime();
  pid[0] = fork();
  if(pid[0] == 0){
    for(i = 0; i < 4; i++)
      close(p[i][0]);
    close(p[1][1]); close(p[2][1]); close(p[3][1]);
    // 20 * 64 = 1280 bytes, more than PIPESIZE, so readers really block.
    for(j = 0; j < 20; j++){ memset(b, 'y', sizeof(b)); write(p[0][1], b, sizeof(b)); }
    close(p[0][1]); exit();
  }
  for(i = 1; i < 5; i++){
    pid[i] = fork();
    if(pid[i] == 0){
      int k;
      if(i == 4){
        for(k = 0; k < 4; k++)
          if(k != 3){ close(p[k][0]); close(p[k][1]); }
        close(p[3][1]);
        if(setworkflow(1, DONATION_TEST_DEADLINE) < 0){
          printf(1, "FAIL donate5 setworkflow\n");
          exit();
        }
        while(read(p[3][0], b, sizeof(b)) > 0);
        close(p[3][0]);
      } else {
        for(k = 0; k < 4; k++){
          if(k != i - 1)
            close(p[k][0]);
          if(k != i)
            close(p[k][1]);
        }
        copy_pipe(p[i - 1][0], p[i][1]);
        close(p[i - 1][0]); close(p[i][1]);
      }
      exit();
    }
  }
  for(i = 0; i < 4; i++){ close(p[i][0]); close(p[i][1]); }
  for(i = 0; i < 5; i++){
    // The hog runs forever, so the first five children reaped are the stages.
    wait();
  }
  j = uptime() - start;
  kill(hog);
  wait();
  {
    struct sched_stats stats;
    schedinfo(&stats);
    printf(1, "CHECK donate5 finish=%d deadline=%d donations=%d cycles=%d misses=%d\n",
           j, DONATION_TEST_DEADLINE, stats.donations, stats.cycles,
           stats.misses);
  }
  tracectl(4);
  write(1, "RESULT donate5\n", 15);
  exit();
}
