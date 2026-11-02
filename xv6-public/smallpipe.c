#include "types.h"
#include "user.h"

int
main(void)
{
  int p[2], pid;
  char buf[64];

  pipe(p);
  pid = fork();
  if(pid == 0){
    close(p[1]);
    read(p[0], buf, sizeof(buf));
    close(p[0]);
    exit();
  }
  close(p[0]);
  write(p[1], "small pipe\n", 11);
  close(p[1]);
  wait();
  write(1, "RESULT smallpipe\n", 18);
  exit();
}
