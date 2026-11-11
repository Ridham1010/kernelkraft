#include "types.h"
#include "user.h"
#include "sched_params.h"

// setworkflow regression checks:
//   A  a refused admission leaves no workflow slot behind
//   B  a process that joins later takes the workflow's existing deadline
//   C  any positive wid is accepted
//   D  forked members are counted, so the workflow outlives its creator
// Each case runs in children because a process joins at most one workflow.

static int fails;

static void
check(char *name, int ok)
{
  printf(1, "CHECK wftest %s %s\n", name, ok ? "ok" : "FAIL");
  if(!ok)
    fails++;
}

// Run setworkflow(wid, dl) in a child that then stays alive until killed;
// report through a pipe whether the call succeeded and the child's deadline.
static int
member(int wid, int dl, int *okp, uint *deadlinep)
{
  int fd[2], pid;
  char r;
  struct procstat st;

  pipe(fd);
  pid = fork();
  if(pid == 0){
    close(fd[0]);
    r = setworkflow(wid, dl) == 0 ? 'y' : 'n';
    write(fd[1], &r, 1);
    close(fd[1]);
    for(;;)
      sleep(100);
  }
  close(fd[1]);
  read(fd[0], &r, 1);
  close(fd[0]);
  *okp = r == 'y';
  *deadlinep = NO_DEADLINE;
  if(procinfo(pid, &st) == 0)
    *deadlinep = st.deadline;
  return pid;
}

static void
reap(int pid)
{
  kill(pid);
  wait();
}

int
main(void)
{
  int a, b, c, oka, okb, okc, fd[2], pid;
  uint da, db, dc;

  // A: slack below MIN_SLACK is refused, and wid 5 must still be usable.
  a = member(5, MIN_SLACK - 1, &oka, &da);
  check("A1 short slack refused", !oka && da == NO_DEADLINE);
  reap(a);
  a = member(5, 500, &oka, &da);
  check("A2 same wid usable after refusal", oka && da != NO_DEADLINE);

  // B: join wid 5 several ticks later, with a different relative deadline.
  sleep(5);
  b = member(5, 900, &okb, &db);
  check("B joiner shares deadline", okb && db == da);
  reap(a);
  reap(b);

  // C: a large wid.
  c = member(1000, 500, &okc, &dc);
  check("C large wid accepted", okc && dc != NO_DEADLINE);
  reap(c);

  // D: the creator forks a member and exits. The survivor must keep the
  // workflow alive, so a later joiner receives the survivor's deadline
  // instead of creating a fresh workflow.
  pipe(fd);
  pid = fork();
  if(pid == 0){
    int g;
    close(fd[0]);
    setworkflow(6, 600);
    g = fork();
    if(g == 0){
      close(fd[1]);
      for(;;)
        sleep(100);
    }
    write(fd[1], &g, sizeof(g));
    exit();
  }
  close(fd[1]);
  c = -1;
  read(fd[0], &c, sizeof(c));
  close(fd[0]);
  wait();               // the creator has exited; its child lives on
  sleep(5);
  dc = NO_DEADLINE;
  {
    struct procstat st;
    if(procinfo(c, &st) == 0)
      dc = st.deadline;
  }
  a = member(6, 600, &oka, &da);
  check("D workflow survives creator exit",
        oka && dc != NO_DEADLINE && da == dc);
  reap(a);
  kill(c);              // orphan: init reaps it

  if(fails == 0)
    write(1, "RESULT wftest\n", 14);
  else
    write(1, "FAIL wftest\n", 12);
  exit();
}
