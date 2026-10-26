#include "types.h"
#include "user.h"
#include "sched_api.h"

static void
burn(int units)
{
  volatile int i;
  volatile int value = 0;

  for(i = 0; i < units * 10000; i++)
    value += i;
  if(value == -1)
    printf(1, "");
}

static int
append_int(char *buf, int pos, int value)
{
  char digits[16];
  int count = 0;
  int i;
  int negative = 0;

  if(value < 0){
    negative = 1;
    value = -value;
  }
  if(value == 0)
    digits[count++] = '0';
  while(value > 0){
    digits[count++] = '0' + value % 10;
    value /= 10;
  }
  if(negative)
    buf[pos++] = '-';
  for(i = count - 1; i >= 0; i--)
    buf[pos++] = digits[i];
  buf[pos] = '\0';
  return pos;
}

int
main(int argc, char *argv[])
{
  int fds[2];
  int stages;
  int work;
  int bytes;
  int deadline;
  int hogs;
  int i;
  int stage1;
  int stage2;
  int hogpid[8];
  int t_start;
  char chunk[64];
  char result[128];
  int n;
  int pos;
  struct sched_stats stats;

  if(argc != 6){
    printf(1, "usage: wfgen <stages> <work> <bytes> <deadline> <hogs>\n");
    exit();
  }
  stages = atoi(argv[1]);
  work = atoi(argv[2]);
  bytes = atoi(argv[3]);
  deadline = atoi(argv[4]);
  hogs = atoi(argv[5]);
  if(hogs < 0 || hogs > 8 || work < 1 || bytes < 1){
    printf(1, "wfgen: invalid arguments\n");
    exit();
  }
  if(pipe(fds) < 0){
    printf(1, "wfgen: pipe failed\n");
    exit();
  }
  t_start = uptime();

  for(i = 0; i < hogs; i++){
    hogpid[i] = fork();
    if(hogpid[i] < 0){
      printf(1, "wfgen: fork failed\n");
      exit();
    }
    if(hogpid[i] == 0){
      close(fds[0]);
      close(fds[1]);
      for(;;)
        burn(work);
    }
  }

  stage1 = fork();
  if(stage1 < 0){
    printf(1, "wfgen: fork failed\n");
    exit();
  }
  if(stage1 == 0){
    int remaining = bytes;
    int amount;
    close(fds[0]);
    while(remaining > 0){
      amount = remaining < sizeof(chunk) ? remaining : sizeof(chunk);
      memset(chunk, 'x', amount);
      burn(work);
      if(write(fds[1], chunk, amount) < 0)
        exit();
      remaining -= amount;
    }
    close(fds[1]);
    exit();
  }

  stage2 = fork();
  if(stage2 < 0){
    printf(1, "wfgen: fork failed\n");
    exit();
  }
  if(stage2 == 0){
    close(fds[1]);
    if(setworkflow(1, deadline) < 0){
      printf(1, "wfgen: workflow rejected by kernel\n");
      close(fds[0]);
      exit();
    }
    if(stages != 2)
      printf(1, "wfgen: unsupported stages\n");
    while((n = read(fds[0], chunk, sizeof(chunk))) > 0){
      burn(work);
    }
    close(fds[0]);
    if(schedinfo(&stats) < 0)
      exit();
    strcpy(result, "RESULT policy=");
    pos = strlen(result);
    pos = append_int(result, pos, stats.policy);
    strcpy(result + pos, " cpus=");
    pos = strlen(result);
    pos = append_int(result, pos, stats.ncpu);
    strcpy(result + pos, " finish=");
    pos = strlen(result);
    pos = append_int(result, pos, uptime() - t_start);
    strcpy(result + pos, " deadline=");
    pos = strlen(result);
    pos = append_int(result, pos, deadline);
    strcpy(result + pos, " miss=");
    pos = strlen(result);
    pos = append_int(result, pos, stats.misses);
    strcpy(result + pos, "\n");
    write(1, result, strlen(result));
    exit();
  }

  close(fds[0]);
  close(fds[1]);
  wait();
  wait();
  for(i = 0; i < hogs; i++){
    kill(hogpid[i]);
    wait();
  }
  exit();
}
