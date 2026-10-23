#include "types.h"
#include "user.h"

int
main(void)
{
  int start;
  int end;

  start = uptime();
  sleep(500);
  end = uptime();
  printf(1, "start %d end %d difference %d\n", start, end, end - start);
  exit();
}
