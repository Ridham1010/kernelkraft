/*
 * Team scheduling parameters. Replace these placeholders for the project
 * configuration; kernel and user code should include this shared header.
 */
#define NO_DEADLINE 0xffffffff
#define MIN_SLACK 20
#define MAX_URGENT 8
#define NWF 8
#define TRACE_SIZE 256
#define MAX_HOGS 8
#define MIN_STAGES 2
#define MAX_STAGES 6
#define MIN_WORK 1
#define MAX_WORK 1000000
#define MIN_BYTES 1
#define MAX_BYTES 1000000
#define DONATION_TEST_DEADLINE 300
