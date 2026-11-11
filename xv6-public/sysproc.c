#include "types.h"
#include "x86.h"
#include "defs.h"
#include "date.h"
#include "param.h"
#include "memlayout.h"
#include "mmu.h"
#include "proc.h"
#include "sched_params.h"
#include "sched_api.h"

int
sys_fork(void)
{
  return fork();
}

int
sys_exit(void)
{
  exit();
  return 0;  // not reached
}

int
sys_wait(void)
{
  return wait();
}

int
sys_kill(void)
{
  int pid;

  if(argint(0, &pid) < 0)
    return -1;
  return kill(pid);
}

int
sys_getpid(void)
{
  return myproc()->pid;
}

int
sys_sbrk(void)
{
  int addr;
  int n;

  if(argint(0, &n) < 0)
    return -1;
  addr = myproc()->sz;
  if(growproc(n) < 0)
    return -1;
  return addr;
}

int
sys_sleep(void)
{
  int n;
  uint ticks0;

  if(argint(0, &n) < 0)
    return -1;
  acquire(&tickslock);
  ticks0 = ticks;
  while(ticks - ticks0 < n){
    if(myproc()->killed){
      release(&tickslock);
      return -1;
    }
    sleep(&ticks, &tickslock);
  }
  release(&tickslock);
  return 0;
}

// return how many clock tick interrupts have occurred
// since start.
int
sys_uptime(void)
{
  uint xticks;

  acquire(&tickslock);
  xticks = ticks;
  release(&tickslock);
  return xticks;
}

int
sys_hello(void)
{
  cprintf("hello from kernel\n");
  return 0;
}

int
sys_add(void)
{
  int a;
  int b;

  if(argint(0, &a) < 0 || argint(1, &b) < 0)
    return -1;
  return a + b;
}

// Stage 2: setsched - set scheduling policy
// policy: 0=rr, 1=edf, 2=edf_donate
int
sys_setsched(void)
{
  int policy;
  if(argint(0, &policy) < 0)
    return -1;
  return sched_setpolicy(policy);
}

// Stage 2: setworkflow - assign process to workflow with deadline
// wid: workflow ID (any positive integer)
// deadline: relative deadline in ticks
int
sys_setworkflow(void)
{
  int wid;
  int deadline;
  
  if(argint(0, &wid) < 0 || argint(1, &deadline) < 0)
    return -1;

  return sys_setworkflow_impl(wid, deadline);
}

// Stage 2: schedinfo - get scheduler statistics
int
sys_schedinfo(void)
{
  struct sched_stats *stats;
  
  if(argptr(0, (char**)&stats, sizeof(struct sched_stats)) < 0)
    return -1;
  
  return sys_schedinfo_impl(stats);
}

int
sys_tracectl(void)
{
  int command;

  if(argint(0, &command) < 0)
    return -1;
  return sys_tracectl_impl(command);
}

int
sys_procinfo(void)
{
  int pid;
  struct procstat *stat;

  if(argint(0, &pid) < 0 ||
     argptr(1, (char**)&stat, sizeof(struct procstat)) < 0)
    return -1;
  return sys_procinfo_impl(pid, stat);
}

// Stage 6: schedtrace - copy trace ring entries to user buffer
// dst: pointer to array of struct trace_ent
// max: maximum number of entries to copy
// Returns: number of entries copied, or -1 on error
int
sys_schedtrace(void)
{
  char *dst;
  int max;

  if(argint(1, &max) < 0)
    return -1;
  if(max < 0 || max > NCPU * TRACE_SIZE)
    return -1;
  if(argptr(0, &dst, max * sizeof(struct trace_ent)) < 0)
    return -1;

  return sys_schedtrace_impl((uint)dst, max);
}
