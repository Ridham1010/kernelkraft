#include "types.h"
#include "user.h"
#include "sched_params.h"
#include "sched_api.h"

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
  int p[4][2], pid[5], hog, i, j;
  char b[64];

  for(i = 0; i < 4; i++)
    pipe(p[i]);
  setworkflow(1, DONATION_TEST_DEADLINE);
  tracectl(3);
  pid[0] = fork();
  if(pid[0] == 0){
    for(i = 0; i < 4; i++)
      close(p[i][0]);
    close(p[1][1]); close(p[2][1]); close(p[3][1]);
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
        while(read(p[3][0], b, sizeof(b)) > 0);
        close(p[3][0]);
      } else {
        for(k = 0; k < 4; k++){
          if(k != i - 1)
            close(p[k][0]);
          if(k != i)
            close(p[k][1]);
        }
        close(p[i - 1][1]);
        copy_pipe(p[i - 1][0], p[i][1]);
        close(p[i - 1][0]); close(p[i][1]);
      }
      exit();
    }
  }
  hog = fork();
  if(hog == 0){ for(j = 0; j < 10000000; j++); exit(); }
  for(i = 0; i < 4; i++){ close(p[i][0]); close(p[i][1]); }
  for(i = 0; i < 6; i++) wait();
  {
    struct sched_stats stats;
    schedinfo(&stats);
    printf(1, "CHECK donate5 donations=%d cycles=%d misses=%d\n",
           stats.donations, stats.cycles, stats.misses);
  }
  tracectl(4);
  write(1, "RESULT donate5\n", 16);
  exit();
}
