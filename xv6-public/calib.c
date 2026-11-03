#include "types.h"
#include "user.h"

#define ITERATIONS 10000000

int
main(int argc, char *argv[])
{
  int n = ITERATIONS;
  int i;
  volatile int sum = 0;
  uint t_start, t_end;
  
  if (argc > 1) {
    n = atoi(argv[1]);
  }
  
  t_start = uptime();
  
  for (i = 0; i < n; i++) {
    sum += i * i;
    sum /= (i + 1);
  }
  
  t_end = uptime();
  
  // Prevent optimization
  if (sum == -1) {
    printf(1, "");
  }
  
  printf(1, "calib: iterations=%d ticks=%d\n", n, t_end - t_start);
  
  exit();
}
