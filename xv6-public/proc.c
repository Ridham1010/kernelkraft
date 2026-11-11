#include "types.h"
#include "defs.h"
#include "param.h"
#include "memlayout.h"
#include "mmu.h"
#include "x86.h"
#include "proc.h"
#include "spinlock.h"
#include "fs.h"
#include "sleeplock.h"
#include "file.h"
#include "sched_params.h"
#include "sched_api.h"

struct {
  struct spinlock lock;
  struct proc proc[NPROC];
} ptable;

static struct proc *initproc;

int nextpid = 1;
extern void forkret(void);
extern void trapret(void);

static void wakeup1(void *chan);

// PAGEBREAK: 17
// Initialize process table lock
void
pinit(void)
{
  initlock(&ptable.lock, "ptable");
}

// Stage 2: scheduling policy globals
int sched_policy = DEFAULT_POLICY;  // 0=rr, 1=edf, 2=edf_donate
uint runcounter = 0;   // Monotonic counter for tie-breaking
static int global_misses;
static int global_rejected;
static int global_donations;
static int global_cycles;
static int donation_debug;
static int cycle_reported;

// Stage 6: Trace ring - per-CPU circular buffer for scheduling events
// All writers must hold ptable.lock (documented in DESIGN.md)
static struct trace_ent trace_ring[NCPU][TRACE_SIZE];
static uint trace_head[NCPU];        // Next write index per CPU
static int trace_enabled = 1;        // Trace enabled by default
static uint trace_seq = 0;           // Global sequence counter

struct donation_event {
  int kind;
  int donor;
  int receiver;
  uint deadline;
};

#define DONATE_EVENT 1
#define CYCLE_EVENT 2

// Stage 2: workflows table. A slot is in use when wid != 0. Slots are found
// by searching for the wid, so any positive wid is valid and NWF only bounds
// how many workflows can be live at once.
struct workflow {
  int wid;             // Workflow ID (0 = unused)
  uint abs_deadline;   // Absolute deadline for this workflow
  int nmembers;        // Number of processes in this workflow
  int misses;          // Number of deadline misses
  int rejected;        // Number of rejected admissions
} workflows[NWF];

// Caller holds ptable.lock. Returns the live slot for wid, or 0.
static struct workflow*
wf_find_locked(int wid)
{
  int i;

  if(wid <= 0)
    return 0;
  for(i = 0; i < NWF; i++)
    if(workflows[i].wid == wid)
      return &workflows[i];
  return 0;
}

// Caller holds ptable.lock. Returns an unused slot, or 0 if the table is full.
static struct workflow*
wf_free_slot_locked(void)
{
  int i;

  for(i = 0; i < NWF; i++)
    if(workflows[i].wid == 0)
      return &workflows[i];
  return 0;
}

// Stage 2: Helper function - read ticks without lock (for use under ptable.lock)
// Not static - called from sysproc.c
inline uint
now_ticks(void)
{
  // Unlocked volatile read of ticks - 32-bit aligned read is atomic on x86
  return ticks;
}

// Stage 6: Trace ring logging function
// Called with ptable.lock held. Records an event to the per-CPU trace ring.
static void
trace_event(int cpu, short pid, short ev, int arg)
{
  if (!trace_enabled)
    return;
  uint tlo, thi;
  rdtsc(&tlo, &thi);
  struct trace_ent *e = &trace_ring[cpu][trace_head[cpu] % TRACE_SIZE];
  e->tlo = tlo;
  e->thi = thi;
  e->cpu = cpu;
  e->pid = pid;
  e->ev = ev;
  e->pad = 0;
  e->arg = arg;
  e->seq = trace_seq++;
  trace_head[cpu]++;
}

// Stage 2: Helper function - compare deadlines with wrap-around safety
// Returns 1 if a is before b (i.e., a's deadline is earlier/more urgent)
static int
dl_before(uint a, uint b)
{
  // NO_DEADLINE (0xffffffff) must be "infinitely late". The signed
  // wrap-around compare below would treat it as -1, i.e. earlier than
  // every real deadline, so it is special-cased first.
  if (a == NO_DEADLINE)
    return 0;
  if (b == NO_DEADLINE)
    return 1;
  // Use signed comparison to handle wrap-around correctly
  // (int)(a - b) < 0 means a is before b in modular arithmetic
  return (int)(a - b) < 0;
}

// Stage 2: Helper function - get effective deadline for a process
// Returns the more urgent (earlier) of deadline and donated
// Firm deadlines (L-16): once a process has missed, its OWN deadline no
// longer counts. A deadline donated by a reader that is still on time does.
static uint
effective(struct proc *p)
{
  uint d = p->missed ? NO_DEADLINE : p->deadline;
  if (p->donated != NO_DEADLINE && dl_before(p->donated, d))
    return p->donated;
  return d;
}

static int
holds_write_end(struct proc *q, struct pipe *pi)
{
  int i;

  if(q->state == UNUSED)
    return 0;
  /*
   * ofile is read without file locks while ptable.lock is held.  This is a
   * known benign race: descriptors are only closed by their owning process.
   */
  for(i = 0; i < NOFILE; i++)
    if(q->ofile[i] && q->ofile[i]->type == FD_PIPE &&
       q->ofile[i]->pipe == pi && q->ofile[i]->writable)
      return 1;
  return 0;
}

// Should h receive the deadline of a reader blocked on the empty pipe pi?
//
// The pipe records its writer side (the last process that wrote to it). If
// that process still holds the write end, it alone is the receiver. Before
// the first write, or once the recorded writer has closed its end or
// exited, nobody is recorded, so every process holding the write end may be
// the one that fills the pipe and all of them receive the donation (L-05).
// Caller holds ptable.lock.
static int
donation_target(struct proc *h, struct proc *reader, struct pipe *pi)
{
  struct proc *w;

  if(h == reader)
    return 0;
  w = pipe_writer(pi);
  if(w && w != reader && holds_write_end(w, pi))
    return h == w;
  return holds_write_end(h, pi);
}

struct donation_frame {
  struct proc *p;
  uint deadline;
  int next;
};

static int
proc_index(struct proc *p)
{
  return p - ptable.proc;
}

static int
donate_walk_locked(struct proc *reader, uint deadline,
                   struct donation_event *events, int *nevents)
{
  struct donation_frame stack[NPROC];
  uchar colour[NPROC];
  struct proc *h;
  int top, idx;

  memset(colour, 0, sizeof(colour));
  top = 0;
  stack[0].p = reader;
  stack[0].deadline = deadline;
  stack[0].next = 0;
  colour[proc_index(reader)] = 1;
  while(top >= 0){
    struct donation_frame *frame = &stack[top];
    if(frame->next >= NPROC){
      colour[proc_index(frame->p)] = 2;
      top--;
      continue;
    }
    idx = frame->next++;
    h = &ptable.proc[idx];
    if(!donation_target(h, frame->p, frame->p->waiting_pipe))
      continue;
    if(h->donated == NO_DEADLINE ||
       dl_before(frame->deadline, h->donated)){
      h->donated = frame->deadline;
      global_donations++;
      trace_event(cpuid(), h->pid, TRACE_DONATE, frame->deadline);
      if(*nevents < DONATION_EVENT_MAX){
        events[*nevents].kind = DONATE_EVENT;
        events[*nevents].donor = frame->p->pid;
        events[*nevents].receiver = h->pid;
        events[*nevents].deadline = frame->deadline;
        (*nevents)++;
      }
    }
    if(h->waiting_pipe == 0 || effective(h) == NO_DEADLINE)
      continue;
    idx = proc_index(h);
    if(colour[idx] == 1){
      if(!cycle_reported && *nevents < DONATION_EVENT_MAX){
        cycle_reported = 1;
        global_cycles++;
        trace_event(cpuid(), frame->p->pid, TRACE_CYCLE, 0);
        events[*nevents].kind = CYCLE_EVENT;
        events[*nevents].donor = 0;
        events[*nevents].receiver = 0;
        (*nevents)++;
      }
      continue;
    }
    if(colour[idx] == 2)
      continue;
    if(top + 1 >= NPROC)
      continue;
    colour[idx] = 1;
    top++;
    stack[top].p = h;
    stack[top].deadline = frame->deadline;
    stack[top].next = 0;
  }
  return 0;
}

static void
print_donation_events(struct donation_event *events, int nevents)
{
  int i;

  if(!donation_debug)
    return;
  for(i = 0; i < nevents; i++)
    if(events[i].kind == DONATE_EVENT)
      cprintf("donate: donor=%d recv=%d dl=%x\n",
              events[i].donor, events[i].receiver,
              events[i].deadline);
    else
      cprintf("donate: cycle\n");
}

// Clear all donated deadlines and emit WITHDRAW trace events.
// Caller holds ptable.lock.
static void
clear_donations_locked(void)
{
  struct proc *q;

  for(q = ptable.proc; q < &ptable.proc[NPROC]; q++)
    if(q->state != UNUSED && q->donated != NO_DEADLINE) {
      trace_event(cpuid(), q->pid, TRACE_WITHDRAW, q->donated);
      q->donated = NO_DEADLINE;
    }
}

static void
recompute_donations_locked(void)
{
  struct proc *q, *h;
  uint d;
  int round, changed;

  clear_donations_locked();
  for(round = 0; round < NPROC + 1; round++){
    changed = 0;
    for(q = ptable.proc; q < &ptable.proc[NPROC]; q++){
      if(q->state == UNUSED || q->waiting_pipe == 0 ||
         (d = effective(q)) == NO_DEADLINE)
        continue;
      for(h = ptable.proc; h < &ptable.proc[NPROC]; h++){
        if(donation_target(h, q, q->waiting_pipe) &&
           (h->donated == NO_DEADLINE || dl_before(d, h->donated))){
          h->donated = d;
          changed = 1;
        }
      }
    }
    if(!changed)
      break;
  }
}

void
pipe_wait_begin(struct pipe *pi)
{
  struct donation_event events[DONATION_EVENT_MAX];
  struct proc *p;
  int nevents;
  uint d;

  p = myproc();
  nevents = 0;
  acquire(&ptable.lock);
  p->waiting_pipe = pi;
  d = effective(p);
  if(sched_policy == 2 && d != NO_DEADLINE)
    donate_walk_locked(p, d, events, &nevents);
  release(&ptable.lock);
  print_donation_events(events, nevents);
}

void
pipe_wait_end(void)
{
  struct proc *q;
  int waiting;

  acquire(&ptable.lock);
  myproc()->waiting_pipe = 0;
  if(sched_policy == 2){
    recompute_donations_locked();
    waiting = 0;
    for(q = ptable.proc; q < &ptable.proc[NPROC]; q++)
      if(q->state != UNUSED && q->waiting_pipe != 0)
        waiting = 1;
    if(!waiting)
      cycle_reported = 0;
  }
  release(&ptable.lock);
}

// Switch the scheduling policy. Donations exist only under policy 2, so
// leaving it withdraws them all (effective() would otherwise keep using
// stale values) and entering it rebuilds them from the current pipe waits.
int
sched_setpolicy(int policy)
{
  if(policy < 0 || policy > 2)
    return -1;
  acquire(&ptable.lock);
  sched_policy = policy;
  if(policy == 2)
    recompute_donations_locked();
  else
    clear_donations_locked();
  release(&ptable.lock);
  return 0;
}

// Admission test, called with ptable.lock held. Returns 0 to admit, or the
// reason for refusal. It changes nothing: the caller does the accounting and
// prints after releasing the lock. check_slack is 0 for a process joining a
// workflow that was already admitted.
static char*
admission_reason_locked(int check_slack, uint deadline)
{
  struct proc *q;
  int urgent = 0;

  if (check_slack && deadline < MIN_SLACK)
    return "slack";
  for (q = ptable.proc; q < &ptable.proc[NPROC]; q++) {
    if (q->state != UNUSED && q->state != ZOMBIE &&
        q->deadline != NO_DEADLINE)
      urgent++;
  }
  if (urgent >= MAX_URGENT)
    return "urgent";
  return 0;
}

static void
mark_missed_locked(struct proc *p)
{
  struct workflow *w;

  if (p->missed || p->deadline == NO_DEADLINE ||
      (int)(now_ticks() - p->deadline) <= 0)
    return;
  p->missed = 1;
  global_misses++;
  trace_event(cpuid(), p->pid, TRACE_DEADLINE_MISS, p->deadline);
  w = wf_find_locked(p->wid);
  if (w)
    w->misses++;
}

// Stage 2: Workflow leave helper - called from exit() with ptable.lock held
static void
wf_leave_locked(struct proc *p)
{
  struct workflow *w = wf_find_locked(p->wid);
  if (w == 0)
    return;  // No workflow, or already freed

  w->nmembers--;
  if (w->nmembers <= 0) {
    // Free the workflow slot
    w->wid = 0;
    w->abs_deadline = 0;
    w->misses = 0;
    w->rejected = 0;
  }
}

// Stage 2: Workflow accessor functions (called with ptable.lock held by caller)

// Get workflow by ID
struct workflow*
get_workflow(int wid)
{
  return wf_find_locked(wid);
}

// Sum of misses across all workflows
int
workflow_misses(void)
{
  int total = 0;
  for (int i = 0; i < NWF; i++) {
    if (workflows[i].wid != 0)
      total += workflows[i].misses;
  }
  return total;
}

// Sum of rejected across all workflows
int
workflow_rejected(void)
{
  int total = 0;
  for (int i = 0; i < NWF; i++) {
    if (workflows[i].wid != 0)
      total += workflows[i].rejected;
  }
  return total;
}

// Stage 2: sys_setworkflow implementation - called from sysproc.c
//
// The first caller for a wid creates the workflow with absolute deadline
// now + deadline. Every later caller joins it and takes the workflow's
// existing deadline, so all members share one deadline no matter which tick
// they call on. Nothing is written to the table until admission has passed,
// so a refused call leaves no slot behind.
int
sys_setworkflow_impl(int wid, int deadline)
{
  struct proc *curproc = myproc();
  struct workflow *w;
  char *reason;
  uint abs;

  // wid 0 means "no workflow"; any positive wid is valid
  if(wid <= 0)
    return -1;

  // Validate deadline: must be > 0
  if(deadline <= 0)
    return -1;

  acquire(&ptable.lock);

  // A process joins at most one workflow (L-02)
  if(curproc->wid != 0){
    release(&ptable.lock);
    return -1;
  }

  w = wf_find_locked(wid);
  if(w){
    abs = w->abs_deadline;
    reason = admission_reason_locked(0, deadline);
  } else {
    abs = now_ticks() + deadline;
    reason = admission_reason_locked(1, deadline);
    if(reason == 0 && wf_free_slot_locked() == 0)
      reason = "table";
  }

  if(reason){
    if(w)
      w->rejected++;
    global_rejected++;
    release(&ptable.lock);
    cprintf("admit: rejected pid=%d wid=%d deadline=%d reason=%s\n",
            curproc->pid, wid, deadline, reason);
    return -1;
  }

  if(w == 0){
    w = wf_free_slot_locked();
    w->wid = wid;
    w->abs_deadline = abs;
    w->nmembers = 0;
    w->misses = 0;
    w->rejected = 0;
  }

  // Assign process to workflow
  curproc->wid = wid;
  curproc->deadline = abs;
  w->nmembers++;

  release(&ptable.lock);
  return 0;
}

// Stage 2: sys_schedinfo implementation - called from sysproc.c
int
sys_schedinfo_impl(struct sched_stats *stats)
{
  // Fill in the stats structure
  stats->policy = sched_policy;
  stats->ncpu = ncpu;
  stats->ticks = now_ticks();
  stats->misses = global_misses;
  stats->donations = global_donations;
  stats->cycles = global_cycles;
  stats->rejected = global_rejected;
  
  return 0;
}

// Stage 6: schedtrace syscall implementation
// Copies trace entries from per-CPU rings to user buffer, oldest-first
// Returns the number of entries copied
int
sys_schedtrace_impl(uint dst, int max)
{
  struct trace_ent *src;
  int available = 0;
  int cpu, idx, count, copied;

  if (max < 0)
    return -1;
  if (max == 0)
    return 0;

  acquire(&ptable.lock);

  // Clamp to the total retained entries; the user buffer is validated first.
  for (cpu = 0; cpu < ncpu; cpu++) {
    count = trace_head[cpu];
    if (count > TRACE_SIZE)
      count = TRACE_SIZE;
    available += count;
  }
  if (available > max)
    available = max;
  if (available == 0) {
    release(&ptable.lock);
    return 0;
  }

  // Copy while locked so a writer cannot change the ring slot mid-copy.
  // copyout does not acquire a lock and therefore does not change lock order.
  copied = 0;
  for (cpu = 0; cpu < ncpu; cpu++) {
    count = trace_head[cpu];
    if (count > TRACE_SIZE)
      count = TRACE_SIZE;
    if (count > available - copied)
      count = available - copied;

    // Oldest entry is at (trace_head[cpu] - count) % TRACE_SIZE
    int start = (trace_head[cpu] >= count) ? trace_head[cpu] - count : trace_head[cpu] - count + TRACE_SIZE;

    for (int i = 0; i < count; i++) {
      idx = (start + i) % TRACE_SIZE;
      src = &trace_ring[cpu][idx];
      if (copyout(myproc()->pgdir, dst + copied * sizeof(struct trace_ent),
                  src, sizeof(struct trace_ent)) < 0) {
        release(&ptable.lock);
        return -1;
      }
      copied++;
    }
    if (copied == available)
      break;
  }

  release(&ptable.lock);
  return copied;
}

int
sys_procinfo_impl(int pid, struct procstat *stat)
{
  struct proc *p;

  acquire(&ptable.lock);
  for(p = ptable.proc; p < &ptable.proc[NPROC]; p++)
    if(p->state != UNUSED && p->pid == pid){
      stat->state = p->state;
      stat->deadline = p->deadline;
      stat->donated = p->donated;
      stat->waiting = p->waiting_pipe != 0;
      release(&ptable.lock);
      return 0;
    }
  release(&ptable.lock);
  return -1;
}

int
sys_tracectl_impl(int command)
{
  // Keep the state changes under ptable.lock, like trace writers.
  acquire(&ptable.lock);
  if(command == 0){
    trace_enabled = 0;
    release(&ptable.lock);
    return 0;
  }
  if(command == 1){
    trace_enabled = 1;
    release(&ptable.lock);
    return 0;
  }
  if(command == 2){
    for(int cpu = 0; cpu < ncpu; cpu++)
      trace_head[cpu] = 0;
    trace_seq = 0;
    release(&ptable.lock);
    return 0;
  }
  if(command == 3){
    donation_debug = 1;
    release(&ptable.lock);
    return 0;
  }
  if(command == 4 || command == 5){
    donation_debug = 0;
    release(&ptable.lock);
    return 0;
  }
  release(&ptable.lock);
  return -1;
}

// Must be called with interrupts disabled
int
cpuid() {
  return mycpu()-cpus;
}

// Must be called with interrupts disabled to avoid the caller being
// rescheduled between reading lapicid and running through the loop.
struct cpu*
mycpu(void)
{
  int apicid, i;
  
  if(readeflags()&FL_IF)
    panic("mycpu called with interrupts enabled\n");
  
  apicid = lapicid();
  // APIC IDs are not guaranteed to be contiguous. Maybe we should have
  // a reverse map, or reserve a register to store &cpus[i].
  for (i = 0; i < ncpu; ++i) {
    if (cpus[i].apicid == apicid)
      return &cpus[i];
  }
  panic("unknown apicid\n");
}

// Disable interrupts so that we are not rescheduled
// while reading proc from the cpu structure
struct proc*
myproc(void) {
  struct cpu *c;
  struct proc *p;
  pushcli();
  c = mycpu();
  p = c->proc;
  popcli();
  return p;
}

//PAGEBREAK: 32
// Look in the process table for an UNUSED proc.
// If found, change state to EMBRYO and initialize
// state required to run in the kernel.
// Otherwise return 0.
static struct proc*
allocproc(void)
{
  struct proc *p;
  char *sp;

  acquire(&ptable.lock);

  for(p = ptable.proc; p < &ptable.proc[NPROC]; p++)
    if(p->state == UNUSED)
      goto found;

  release(&ptable.lock);
  return 0;

found:
  p->state = EMBRYO;
  p->pid = nextpid++;

  // Stage 2: Initialize scheduling fields
  p->wid = 0;
  p->deadline = NO_DEADLINE;
  p->donated = NO_DEADLINE;
  p->waiting_pipe = 0;
  p->last_run = 0;
  p->missed = 0;

  release(&ptable.lock);

  // Allocate kernel stack.
  if((p->kstack = kalloc()) == 0){
    p->state = UNUSED;
    return 0;
  }
  sp = p->kstack + KSTACKSIZE;

  // Leave room for trap frame.
  sp -= sizeof *p->tf;
  p->tf = (struct trapframe*)sp;

  // Set up new context to start executing at forkret,
  // which returns to trapret.
  sp -= 4;
  *(uint*)sp = (uint)trapret;

  sp -= sizeof *p->context;
  p->context = (struct context*)sp;
  memset(p->context, 0, sizeof *p->context);
  p->context->eip = (uint)forkret;

  return p;
}

//PAGEBREAK: 32
// Set up first user process.
void
userinit(void)
{
  struct proc *p;
  extern char _binary_initcode_start[], _binary_initcode_size[];

  p = allocproc();
  
  initproc = p;
  if((p->pgdir = setupkvm()) == 0)
    panic("userinit: out of memory?");
  inituvm(p->pgdir, _binary_initcode_start, (int)_binary_initcode_size);
  p->sz = PGSIZE;
  memset(p->tf, 0, sizeof(*p->tf));
  p->tf->cs = (SEG_UCODE << 3) | DPL_USER;
  p->tf->ds = (SEG_UDATA << 3) | DPL_USER;
  p->tf->es = p->tf->ds;
  p->tf->ss = p->tf->ds;
  p->tf->eflags = FL_IF;
  p->tf->esp = PGSIZE;
  p->tf->eip = 0;  // beginning of initcode.S

  safestrcpy(p->name, "initcode", sizeof(p->name));
  p->cwd = namei("/");

  // this assignment to p->state lets other cores
  // run this process. the acquire forces the above
  // writes to be visible, and the lock is also needed
  // because the assignment might not be atomic.
  acquire(&ptable.lock);

  p->state = RUNNABLE;

  release(&ptable.lock);
}

// Grow current process's memory by n bytes.
// Return 0 on success, -1 on failure.
int
growproc(int n)
{
  uint sz;
  struct proc *curproc = myproc();

  sz = curproc->sz;
  if(n > 0){
    if((sz = allocuvm(curproc->pgdir, sz, sz + n)) == 0)
      return -1;
  } else if(n < 0){
    if((sz = deallocuvm(curproc->pgdir, sz, sz + n)) == 0)
      return -1;
  }
  curproc->sz = sz;
  switchuvm(curproc);
  return 0;
}

// Create a new process copying p as the parent.
// Sets up stack to return as if from system call.
// Caller must set state of returned proc to RUNNABLE.
int
fork(void)
{
  int i, pid;
  struct proc *np;
  struct proc *curproc = myproc();
  struct proc *q;
  struct donation_event events[DONATION_EVENT_MAX];
  int nevents = 0;
  uint d;

  // Allocate process.
  if((np = allocproc()) == 0){
    return -1;
  }

  // Copy process state from proc.
  if((np->pgdir = copyuvm(curproc->pgdir, curproc->sz)) == 0){
    kfree(np->kstack);
    np->kstack = 0;
    np->state = UNUSED;
    return -1;
  }
  np->sz = curproc->sz;
  np->parent = curproc;
  *np->tf = *curproc->tf;

  // Clear %eax so that fork returns 0 in the child.
  np->tf->eax = 0;

  for(i = 0; i < NOFILE; i++)
    if(curproc->ofile[i])
      np->ofile[i] = filedup(curproc->ofile[i]);
  np->cwd = idup(curproc->cwd);

  safestrcpy(np->name, curproc->name, sizeof(curproc->name));

  pid = np->pid;

  acquire(&ptable.lock);

  // Stage 2: the child inherits its parent's workflow and own deadline and
  // is counted as a member, so exit() can decrement nmembers symmetrically.
  np->wid = curproc->wid;
  np->deadline = curproc->deadline;
  np->donated = NO_DEADLINE;  // Donated deadline is not inherited
  np->waiting_pipe = 0;
  np->last_run = 0;
  np->missed = 0;
  {
    struct workflow *w = wf_find_locked(np->wid);
    if(w)
      w->nmembers++;
  }

  // Donation is otherwise decided when a reader goes to sleep. If the child
  // has just inherited the write end of a pipe that an urgent reader is
  // already asleep on, that reader now depends on the child too.
  if(sched_policy == 2)
    for(q = ptable.proc; q < &ptable.proc[NPROC]; q++)
      if(q->state != UNUSED && q->waiting_pipe != 0 &&
         (d = effective(q)) != NO_DEADLINE &&
         donation_target(np, q, q->waiting_pipe))
        donate_walk_locked(q, d, events, &nevents);

  np->state = RUNNABLE;

  release(&ptable.lock);
  print_donation_events(events, nevents);

  return pid;
}

// Exit the current process.  Does not return.
// An exited process remains in the zombie state
// until its parent calls wait() to find out it exited.
void
exit(void)
{
  struct proc *curproc = myproc();
  struct proc *p;
  int fd;

  if(curproc == initproc)
    panic("init exiting");

  // Close all open files.
  for(fd = 0; fd < NOFILE; fd++){
    if(curproc->ofile[fd]){
      fileclose(curproc->ofile[fd]);
      curproc->ofile[fd] = 0;
    }
  }

  begin_op();
  iput(curproc->cwd);
  end_op();
  curproc->cwd = 0;

  acquire(&ptable.lock);

  curproc->waiting_pipe = 0;
  if(sched_policy == 2)
    recompute_donations_locked();
  mark_missed_locked(curproc);
  // Stage 2: Leave workflow if part of one
  wf_leave_locked(curproc);

  // Parent might be sleeping in wait().
  wakeup1(curproc->parent);

  // Pass abandoned children to init.
  for(p = ptable.proc; p < &ptable.proc[NPROC]; p++){
    if(p->parent == curproc){
      p->parent = initproc;
      if(p->state == ZOMBIE)
        wakeup1(initproc);
    }
  }

  // Jump into the scheduler, never to return.
  curproc->state = ZOMBIE;
  sched();
  panic("zombie exit");
}

// Wait for a child process to exit and return its pid.
// Return -1 if this process has no children.
int
wait(void)
{
  struct proc *p;
  int havekids, pid;
  struct proc *curproc = myproc();
  
  acquire(&ptable.lock);
  for(;;){
    // Scan through table looking for exited children.
    havekids = 0;
    for(p = ptable.proc; p < &ptable.proc[NPROC]; p++){
      if(p->parent != curproc)
        continue;
      havekids = 1;
      if(p->state == ZOMBIE){
        // Found one.
        pid = p->pid;
        kfree(p->kstack);
        p->kstack = 0;
        freevm(p->pgdir);
        p->pid = 0;
        p->parent = 0;
        p->name[0] = 0;
        p->killed = 0;
        p->state = UNUSED;
        release(&ptable.lock);
        return pid;
      }
    }

    // No point waiting if we don't have any children.
    if(!havekids || curproc->killed){
      release(&ptable.lock);
      return -1;
    }

    // Wait for children to exit.  (See wakeup1 call in proc_exit.)
    sleep(curproc, &ptable.lock);  //DOC: wait-sleep
  }
}

//PAGEBREAK: 42
// Per-CPU process scheduler.
// Each CPU calls scheduler() after setting itself up.
// Scheduler never returns.  It loops, doing:
//  - choose a process to run
//  - swtch to start running that process
//  - eventually that process transfers control
//      via swtch back to the scheduler.
void
scheduler(void)
{
  struct proc *p;
  struct cpu *c = mycpu();
  c->proc = 0;
  
  for(;;){
    // Enable interrupts on this processor.
    sti();

    // Policy 0: Original round-robin scheduler (unchanged)
    if (sched_policy == 0) {
      acquire(&ptable.lock);
      for(p = ptable.proc; p < &ptable.proc[NPROC]; p++)
        if(p->state != UNUSED)
          mark_missed_locked(p);
      for(p = ptable.proc; p < &ptable.proc[NPROC]; p++){
        if(p->state != RUNNABLE)
          continue;

        // Switch to chosen process.  It is the process's job
        // to release ptable.lock and then reacquire it
        // before jumping back to us.
        c->proc = p;
        switchuvm(p);
        p->state = RUNNING;
        trace_event(cpuid(), p->pid, TRACE_SWITCH_IN, 0);

        swtch(&(c->scheduler), p->context);
        switchkvm();

        // Process is done running for now.
        // It should have changed its p->state before coming back.
        trace_event(cpuid(), p->pid, TRACE_SWITCH_OUT, 0);
        c->proc = 0;
      }
      release(&ptable.lock);
    }
    // Policy 1: EDF, Policy 2: EDF with donation (same scheduling logic for now)
    else {
      acquire(&ptable.lock);
      struct proc *best = 0;
      
      for(p = ptable.proc; p < &ptable.proc[NPROC]; p++)
        if(p->state != UNUSED)
          mark_missed_locked(p);

      // Scan all NPROC slots choosing best among RUNNABLE
      for(p = ptable.proc; p < &ptable.proc[NPROC]; p++){
        if(p->state != RUNNABLE)
          continue;
        
        if (best == 0) {
          best = p;
        } else {
          uint eff_p = effective(p);
          uint eff_best = effective(best);
          
          // Better if dl_before(effective(p), effective(best))
          if (dl_before(eff_p, eff_best)) {
            best = p;
          }
          // Equal effective deadlines: tie-break on least-recently-run
          // Use < (not <=) to avoid index starvation
          else if (eff_p == eff_best && p->last_run < best->last_run) {
            best = p;
          }
        }
      }
      
      if (best) {
        best->last_run = ++runcounter;
        
        // Switch to chosen process
        c->proc = best;
        switchuvm(best);
        best->state = RUNNING;
        trace_event(cpuid(), best->pid, TRACE_SWITCH_IN, 0);

        swtch(&(c->scheduler), best->context);
        switchkvm();

        // Process is done running for now.
        trace_event(cpuid(), best->pid, TRACE_SWITCH_OUT, 0);
        c->proc = 0;
      }
      release(&ptable.lock);
    }
  }
}

// Enter scheduler.  Must hold only ptable.lock
// and have changed proc->state. Saves and restores
// intena because intena is a property of this
// kernel thread, not this CPU. It should
// be proc->intena and proc->ncli, but that would
// break in the few places where a lock is held but
// there's no process.
void
sched(void)
{
  int intena;
  struct proc *p = myproc();

  if(!holding(&ptable.lock))
    panic("sched ptable.lock");
  if(mycpu()->ncli != 1)
    panic("sched locks");
  if(p->state == RUNNING)
    panic("sched running");
  if(readeflags()&FL_IF)
    panic("sched interruptible");
  intena = mycpu()->intena;
  swtch(&p->context, mycpu()->scheduler);
  mycpu()->intena = intena;
}

// Give up the CPU for one scheduling round.
void
yield(void)
{
  acquire(&ptable.lock);  //DOC: yieldlock
  myproc()->state = RUNNABLE;
  sched();
  release(&ptable.lock);
}

// A fork child's very first scheduling by scheduler()
// will swtch here.  "Return" to user space.
void
forkret(void)
{
  static int first = 1;
  // Still holding ptable.lock from scheduler.
  release(&ptable.lock);

  if (first) {
    // Some initialization functions must be run in the context
    // of a regular process (e.g., they call sleep), and thus cannot
    // be run from main().
    first = 0;
    iinit(ROOTDEV);
    initlog(ROOTDEV);
  }

  // Return to "caller", actually trapret (see allocproc).
}

// Atomically release lock and sleep on chan.
// Reacquires lock when awakened.
void
sleep(void *chan, struct spinlock *lk)
{
  struct proc *p = myproc();
  
  if(p == 0)
    panic("sleep");

  if(lk == 0)
    panic("sleep without lk");

  // Must acquire ptable.lock in order to
  // change p->state and then call sched.
  // Once we hold ptable.lock, we can be
  // guaranteed that we won't miss any wakeup
  // (wakeup runs with ptable.lock locked),
  // so it's okay to release lk.
  if(lk != &ptable.lock){  //DOC: sleeplock0
    acquire(&ptable.lock);  //DOC: sleeplock1
    release(lk);
  }
  // Go to sleep.
  p->chan = chan;
  p->state = SLEEPING;

  sched();

  // Tidy up.
  p->chan = 0;

  // Reacquire original lock.
  if(lk != &ptable.lock){  //DOC: sleeplock2
    release(&ptable.lock);
    acquire(lk);
  }
}

//PAGEBREAK!
// Wake up all processes sleeping on chan.
// The ptable lock must be held.
static void
wakeup1(void *chan)
{
  struct proc *p;

  for(p = ptable.proc; p < &ptable.proc[NPROC]; p++)
    if(p->state == SLEEPING && p->chan == chan)
      p->state = RUNNABLE;
}

// Wake up all processes sleeping on chan.
void
wakeup(void *chan)
{
  acquire(&ptable.lock);
  wakeup1(chan);
  release(&ptable.lock);
}

// Kill the process with the given pid.
// Process won't exit until it returns
// to user space (see trap in trap.c).
int
kill(int pid)
{
  struct proc *p;

  acquire(&ptable.lock);
  for(p = ptable.proc; p < &ptable.proc[NPROC]; p++){
    if(p->pid == pid){
      p->killed = 1;
      // Wake process from sleep if necessary.
      if(p->state == SLEEPING)
        p->state = RUNNABLE;
      release(&ptable.lock);
      return 0;
    }
  }
  release(&ptable.lock);
  return -1;
}

//PAGEBREAK: 36
// Print a process listing to console.  For debugging.
// Runs when user types ^P on console.
// No lock to avoid wedging a stuck machine further.
void
procdump(void)
{
  static char *states[] = {
  [UNUSED]    "unused",
  [EMBRYO]    "embryo",
  [SLEEPING]  "sleep ",
  [RUNNABLE]  "runble",
  [RUNNING]   "run   ",
  [ZOMBIE]    "zombie"
  };
  int i;
  struct proc *p;
  char *state;
  uint pc[10];

  for(p = ptable.proc; p < &ptable.proc[NPROC]; p++){
    if(p->state == UNUSED)
      continue;
    if(p->state >= 0 && p->state < NELEM(states) && states[p->state])
      state = states[p->state];
    else
      state = "???";
    cprintf("%d %s %s", p->pid, state, p->name);
    if(p->state == SLEEPING){
      getcallerpcs((uint*)p->context->ebp+2, pc);
      for(i=0; i<10 && pc[i] != 0; i++)
        cprintf(" %p", pc[i]);
    }
    cprintf("\n");
  }
}
