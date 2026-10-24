#include "types.h"
#include "stat.h"
#include "user.h"
#include "sched_params.h"

#define LOOPS 50000000  // Adjust to burn ~5 seconds of CPU

void
busy_wait(int loops)
{
  volatile int i, j, k;
  for (i = 0; i < loops; i++) {
    j = i * i;
    k = j / (i + 1);
    if (k < 0) k = -k;
  }
}

void
itoa(int n, char *buf)
{
  int i = 0;
  int neg = 0;
  char tmp[16];
  
  if (n == 0) {
    buf[0] = '0';
    buf[1] = '\0';
    return;
  }
  
  if (n < 0) {
    neg = 1;
    n = -n;
  }
  
  while (n > 0) {
    tmp[i++] = '0' + (n % 10);
    n /= 10;
  }
  
  int j = 0;
  if (neg) {
    buf[j++] = '-';
  }
  
  while (i > 0) {
    buf[j++] = tmp[--i];
  }
  buf[j] = '\0';
}

int
main(int argc, char *argv[])
{
  int pid1, pid2;
  char buf[128];
  char pid_str[16];
  char time_str[16];
  int idx;
  
  pid1 = fork();
  if (pid1 < 0) {
    printf(1, "fork failed\n");
    exit();
  }
  
  if (pid1 == 0) {
    // Child A - workflow 1, deadline 100 ticks
    if (setworkflow(1, 100) < 0) {
      printf(1, "child A: setworkflow failed\n");
      exit();
    }
    
    busy_wait(LOOPS);
    
    // Build string manually: "child A pid=X done at Y\n"
    strcpy(buf, "child A pid=");
    itoa(getpid(), pid_str);
    idx = strlen(buf);
    strcpy(buf + idx, pid_str);
    strcpy(buf + strlen(buf), " done at ");
    itoa(uptime(), time_str);
    idx = strlen(buf);
    strcpy(buf + idx, time_str);
    buf[strlen(buf)] = '\n';
    buf[strlen(buf) + 1] = '\0';
    write(1, buf, strlen(buf));
    exit();
  }
  
  pid2 = fork();
  if (pid2 < 0) {
    printf(1, "fork failed\n");
    exit();
  }
  
  if (pid2 == 0) {
    // Child B - workflow 2, deadline 200 ticks
    if (setworkflow(2, 200) < 0) {
      printf(1, "child B: setworkflow failed\n");
      exit();
    }
    
    busy_wait(LOOPS);
    
    // Build string manually: "child B pid=X done at Y\n"
    strcpy(buf, "child B pid=");
    itoa(getpid(), pid_str);
    idx = strlen(buf);
    strcpy(buf + idx, pid_str);
    strcpy(buf + strlen(buf), " done at ");
    itoa(uptime(), time_str);
    idx = strlen(buf);
    strcpy(buf + idx, time_str);
    buf[strlen(buf)] = '\n';
    buf[strlen(buf) + 1] = '\0';
    write(1, buf, strlen(buf));
    exit();
  }
  
  // Parent waits for both children
  wait();
  wait();
  
  exit();
}
