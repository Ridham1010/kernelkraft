/*
 * Team scheduling parameters. This is the one place they are defined;
 * kernel and user code both include this header.
 */
#define NO_DEADLINE 0xffffffff
/* Policy at boot: 0=rr, 1=edf, 2=edf_donate. The assignment replaces
 * round-robin, so the kernel starts in EDF with donation; rr and edf stay
 * selectable through setsched for the baseline measurements. */
#define DEFAULT_POLICY 2
/* Admission: a new workflow needs at least this many ticks of slack. */
#define MIN_SLACK 20
/* Admission: cap on live processes that carry their own deadline.
 * Equal to NPROC, so it cannot refuse a process the table could hold. */
#define MAX_URGENT 64
/* Maximum number of workflows alive at once (any positive wid is valid). */
#define NWF 16
#define TRACE_SIZE 256
/* Donation events buffered per pipe wait for the print mode (on-stack). */
#define DONATION_EVENT_MAX 32
#define MAX_HOGS 8
#define MIN_STAGES 2
#define MAX_STAGES 6
#define MIN_WORK 1
#define MAX_WORK 1000000
#define MIN_BYTES 1
#define MAX_BYTES 1000000
#define DONATION_TEST_DEADLINE 300
