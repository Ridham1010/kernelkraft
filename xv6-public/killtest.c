#include "types.h"
#include "user.h"
#include "sched_params.h"

// Two donors lend to one receiver; each is killed while its donation is
// active. The receiver has no deadline of its own, so its donated field
// shows exactly what the donors lend it:
//   after the first kill  -> still the deadline (the other donor remains)
//   after the second kill -> NO_DEADLINE (nothing left to lend)
// The donors join workflow 1 on different ticks, which also checks that a
// later joiner takes the workflow's existing deadline.

static void
donor_main(int hold[2], int waitp[2])
{
  char c;

  close(hold[0]); close(hold[1]); close(waitp[1]);
  if(setworkflow(1, DONATION_TEST_DEADLINE) < 0){
    printf(1, "FAIL killtest setworkflow\n");
    exit();
  }
  read(waitp[0], &c, 1);
  exit();
}

int
main(void)
{
  int hold[2], waitp[2], receiver, donor, donor2, found, ok;
  struct procstat st;
  char c;

  pipe(hold); pipe(waitp);
  tracectl(3);
  receiver = fork();
  if(receiver == 0){
    // Keeps the write end of waitp, and blocks on hold, which only the
    // parent can fill. It therefore stays alive holding the donation.
    close(hold[1]); close(waitp[0]);
    read(hold[0], &c, 1);
    exit();
  }
  donor = fork();
  if(donor == 0)
    donor_main(hold, waitp);
  sleep(3);
  donor2 = fork();
  if(donor2 == 0)
    donor_main(hold, waitp);
  close(hold[0]); close(waitp[0]); close(waitp[1]);
  sleep(10);
  ok = 1;
  kill(donor);
  wait();
  if(procinfo(receiver, &st) < 0){
    printf(1, "CHECK killtest lookup=fail\n");
    ok = 0;
  } else {
    printf(1, "CHECK after_one_kill donated=%x\n", st.donated);
    if(st.donated == NO_DEADLINE)
      ok = 0;
  }
  kill(donor2);
  wait();
  found = procinfo(receiver, &st) == 0;
  if(found){
    printf(1, "CHECK after_two_kills donated=%x\n", st.donated);
  }
  if(ok && found && st.donated == NO_DEADLINE)
    write(1, "RESULT killtest\n", 16);
  else
    write(1, "FAIL killtest\n", 14);
  kill(receiver);
  wait();
  tracectl(4);
  exit();
}
