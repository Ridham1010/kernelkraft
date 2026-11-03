#ifndef SCHED_API_H
#define SCHED_API_H

#include "types.h"

// Trace ring size (shared between kernel and user)
#define TRACE_SIZE 256

// Shared scheduler statistics structure (kernel and user)
struct sched_stats {
  int policy;      // Current scheduling policy (0=rr, 1=edf, 2=edf_donate)
  int ncpu;        // Number of CPUs
  uint ticks;      // Current tick count
  int misses;      // Number of deadline misses
  int donations;   // Number of priority donations
  int cycles;      // Number of scheduling cycles
  int rejected;    // Number of rejected workflow admissions
};

// Trace ring structure and event types
#define TRACE_SWITCH_IN   1
#define TRACE_SWITCH_OUT  2
#define TRACE_DONATE      3
#define TRACE_WITHDRAW    4
#define TRACE_CYCLE       5
#define TRACE_DEADLINE_MISS 6

struct trace_ent {
  uint tlo;       // TSC low 32 bits
  uint thi;       // TSC high 32 bits
  short cpu;      // CPU ID
  short pid;      // Process ID
  short ev;       // Event type (TRACE_*)
  short pad;      // Padding for alignment
  int arg;        // Event-specific argument (deadline, etc.)
  uint seq;       // Global sequence number
};

struct procstat {
  int state;
  uint deadline;
  uint donated;
  int waiting;
};

#endif // SCHED_API_H
