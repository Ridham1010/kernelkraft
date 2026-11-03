#include "types.h"
#include "user.h"
#include "sched_params.h"

int
main(void)
{
  int a[2], b[2], p1, p2;
  char c;

  pipe(a); pipe(b);
  setworkflow(1, DONATION_TEST_DEADLINE);
  p1 = fork();
  if(p1 == 0){
    close(a[0]); close(b[1]);
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
  tracectl(3);
  sleep(20);
  kill(p1); kill(p2);
  wait(); wait();
  tracectl(4);
  write(1, "RESULT cycletest\n", 18);
  exit();
}
