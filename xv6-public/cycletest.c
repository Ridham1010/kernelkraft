#include "types.h"
#include "user.h"
#include "sched_params.h"

// Pipe cycle between two processes: p1 reads b then writes a, p2 reads a
// then writes b. Both block forever. p1 has a deadline, so its donation
// walks p1 -> p2 -> p1; the kernel must report the cycle and keep running.

int
main(void)
{
  int a[2], b[2], p1, p2;
  char c;

  pipe(a); pipe(b);
  tracectl(3);
  p1 = fork();
  if(p1 == 0){
    close(a[0]); close(b[1]);
    if(setworkflow(1, DONATION_TEST_DEADLINE) < 0){
      printf(1, "FAIL cycletest setworkflow\n");
      exit();
    }
    read(b[0], &c, 1);
    write(a[1], &c, 1);
    exit();
  }
  p2 = fork();
  if(p2 == 0){
    close(a[1]); close(b[0]);
    read(a[0], &c, 1);
    write(b[1], &c, 1);
    exit();
  }
  close(a[0]); close(a[1]); close(b[0]); close(b[1]);
  sleep(20);
  kill(p1); kill(p2);
  wait(); wait();
  tracectl(4);
  write(1, "RESULT cycletest\n", 17);
  exit();
}
