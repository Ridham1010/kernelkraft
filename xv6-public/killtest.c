#include "types.h"
#include "user.h"
#include "sched_params.h"

int
main(void)
{
  int hold[2], waitp[2], receiver, donor, donor2, found;
  struct procstat st;
  char c;

  pipe(hold); pipe(waitp);
  setworkflow(1, DONATION_TEST_DEADLINE);
  tracectl(3);
  receiver = fork();
  if(receiver == 0){
    close(hold[1]); close(waitp[0]);
    read(hold[0], &c, 1);
    exit();
  }
  donor = fork();
  if(donor == 0){
    close(hold[0]); close(hold[1]); close(waitp[1]);
    read(waitp[0], &c, 1);
    exit();
  }
  donor2 = fork();
  if(donor2 == 0){
    close(hold[0]); close(hold[1]); close(waitp[1]);
    read(waitp[0], &c, 1);
    exit();
  }
  close(hold[0]); close(waitp[0]); close(waitp[1]);
  sleep(10);
  kill(donor);
  wait();
  if(procinfo(receiver, &st) < 0)
    printf(1, "CHECK killtest lookup=fail\n");
  else
    printf(1, "CHECK after_one_kill donated=%x\n", st.donated);
  kill(donor2);
  wait();
  found = procinfo(receiver, &st) == 0;
  if(found){
    printf(1, "CHECK after_two_kills donated=%x\n", st.donated);
  }
  if(found && st.donated == NO_DEADLINE)
    write(1, "RESULT killtest\n", 17);
  else
    write(1, "FAIL killtest\n", 15);
  kill(receiver);
  wait();
  tracectl(4);
  exit();
}
