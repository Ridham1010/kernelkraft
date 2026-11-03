#include "types.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int cmd;
  
  if (argc != 2) {
    printf(1, "usage: tracectl <command>\n");
    printf(1, "  0: disable trace\n");
    printf(1, "  1: enable trace\n");
    printf(1, "  2: clear trace rings\n");
    printf(1, "  3: enable donation debug\n");
    printf(1, "  4: disable donation debug\n");
    exit();
  }
  
  cmd = atoi(argv[1]);
  
  if (tracectl(cmd) < 0) {
    printf(1, "tracectl: failed\n");
    exit();
  }
  
  printf(1, "tracectl: command %d executed\n", cmd);
  exit();
}
