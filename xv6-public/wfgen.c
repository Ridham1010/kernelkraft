#include "types.h"
#include "user.h"
#include "sched_api.h"
#include "sched_params.h"

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

static void
close_pipes(int pipes[MAX_STAGES - 1][2], int count)
{
  int i;

  for(i = 0; i < count; i++){
    close(pipes[i][0]);
    close(pipes[i][1]);
  }
}

static void
close_unused_pipes(int pipes[MAX_STAGES - 1][2], int count, int in, int out)
{
  int i;

  for(i = 0; i < count; i++){
    if(pipes[i][0] != in)
      close(pipes[i][0]);
    if(pipes[i][1] != out)
      close(pipes[i][1]);
  }
}

static void
run_stage(int stage, int stages, int pipes[MAX_STAGES - 1][2],
          int work, int bytes, int deadline, int start)
{
  char chunk[64];
  int in;
  int out;
  int n;
  int remaining;
  int amount;
  int result_pos;
  char result[128];
  struct sched_stats stats;

  in = -1;
  out = -1;
  if(stage > 0)
    in = pipes[stage - 1][0];
  if(stage < stages - 1)
    out = pipes[stage][1];

  // Closing unrelated ends is required for downstream readers to observe EOF.
  close_unused_pipes(pipes, stages - 1, in, out);
  if(stage == stages - 1){
    // Admission belongs to the final stage so one workflow has one deadline.
    if(setworkflow(1, deadline) < 0){
      printf(1, "wfgen: workflow rejected by kernel\n");
      exit();
    }
  }

  if(stage == 0){
    remaining = bytes;
    while(remaining > 0){
      amount = remaining < sizeof(chunk) ? remaining : sizeof(chunk);
      memset(chunk, 'x', amount);
      burn(work);
      if(write(out, chunk, amount) < 0)
        break;
      remaining -= amount;
    }
  } else {
    while((n = read(in, chunk, sizeof(chunk))) > 0){
      burn(work);
      if(stage < stages - 1 && write(out, chunk, n) < 0)
        break;
    }
  }

  if(in >= 0)
    close(in);
  if(out >= 0)
    close(out);
  if(stage != stages - 1)
    exit();

  if(schedinfo(&stats) < 0)
    exit();
  strcpy(result, "RESULT policy=");
  result_pos = strlen(result);
  result_pos = append_int(result, result_pos, stats.policy);
  strcpy(result + result_pos, " cpus=");
  result_pos = strlen(result);
  result_pos = append_int(result, result_pos, stats.ncpu);
  strcpy(result + result_pos, " finish=");
  result_pos = strlen(result);
  result_pos = append_int(result, result_pos, uptime() - start);
  strcpy(result + result_pos, " deadline=");
  result_pos = strlen(result);
  result_pos = append_int(result, result_pos, deadline);
  strcpy(result + result_pos, " miss=");
  result_pos = strlen(result);
  result_pos = append_int(result, result_pos, stats.misses);
  strcpy(result + result_pos, "\n");
  // One write keeps the machine-readable record intact on xv6's console.
  write(1, result, strlen(result));
  exit();
}

int
main(int argc, char *argv[])
{
  int pipes[MAX_STAGES - 1][2];
  int hog_pid[MAX_HOGS];
  int stages;
  int work;
  int bytes;
  int deadline;
  int hogs;
  int start;
  int i;
  int pid;

  if(argc != 6){
    printf(1, "usage: wfgen <stages> <work> <bytes> <deadline> <hogs>\n");
    exit();
  }
  stages = atoi(argv[1]);
  work = atoi(argv[2]);
  bytes = atoi(argv[3]);
  deadline = atoi(argv[4]);
  hogs = atoi(argv[5]);
  if(stages < MIN_STAGES || stages > MAX_STAGES ||
     work < MIN_WORK || work > MAX_WORK ||
     bytes < MIN_BYTES || bytes > MAX_BYTES ||
     hogs < 0 || hogs > MAX_HOGS){
    printf(1, "wfgen: invalid arguments\n");
    exit();
  }

  for(i = 0; i < stages - 1; i++)
    if(pipe(pipes[i]) < 0){
      printf(1, "wfgen: pipe failed\n");
      exit();
    }
  start = uptime();

  // Hogs are forked first so they compete with every pipeline stage.
  for(i = 0; i < hogs; i++){
    hog_pid[i] = fork();
    if(hog_pid[i] < 0){
      printf(1, "wfgen: fork failed\n");
      exit();
    }
    if(hog_pid[i] == 0){
      close_pipes(pipes, stages - 1);
      for(;;)
        burn(work);
    }
  }

  for(i = 0; i < stages; i++){
    pid = fork();
    if(pid < 0){
      printf(1, "wfgen: fork failed\n");
      exit();
    }
    if(pid == 0)
      run_stage(i, stages, pipes, work, bytes, deadline, start);
  }

  close_pipes(pipes, stages - 1);
  for(i = 0; i < stages; i++)
    wait();
  for(i = 0; i < hogs; i++){
    kill(hog_pid[i]);
    wait();
  }
  exit();
}
