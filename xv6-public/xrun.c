#include "types.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int pid;
  if(argc < 3){
    printf(1, "usage: xrun nonce cmd args...\n");
    exit();
  }
  pid = fork();
  if(pid == 0){
    exec(argv[2], &argv[2]);
    printf(1, "@@EXECFAIL %s\n", argv[1]);
    exit();
  }
  if(pid < 0){
    printf(1, "@@EXECFAIL %s\n", argv[1]);
    exit();
  }
  wait();
  printf(1, "@@DONE %s\n", argv[1]);
  exit();
}
