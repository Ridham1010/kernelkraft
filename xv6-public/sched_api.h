#ifndef SCHED_API_H
#define SCHED_API_H

#include "types.h"

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

#endif // SCHED_API_H
