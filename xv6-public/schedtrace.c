#include "types.h"
#include "user.h"
#include "sched_api.h"

static void
itoa(int n, char *buf)
{
  int i = 0;
  int neg = 0;
  char tmp[16];
  
  if (n == 0) {
    buf[0] = '0';
    buf[1] = '\0';
    return;
  }
  
  if (n < 0) {
    neg = 1;
    n = -n;
  }
  
  while (n > 0) {
    tmp[i++] = '0' + (n % 10);
    n /= 10;
  }
  
  int j = 0;
  if (neg) {
    buf[j++] = '-';
  }
  
  while (i > 0) {
    buf[j++] = tmp[--i];
  }
  buf[j] = '\0';
}

static void
append_str(char *buf, int *pos, const char *str)
{
  while (*str) {
    buf[(*pos)++] = *str++;
  }
}

static void
append_int(char *buf, int *pos, int value)
{
  char num[16];
  itoa(value, num);
  append_str(buf, pos, num);
}

static void
append_hex(char *buf, int *pos, uint value)
{
  char hex_digits[] = "0123456789abcdef";
  char tmp[16];
  int i = 0;
  
  if (value == 0) {
    buf[(*pos)++] = '0';
    buf[(*pos)++] = 'x';
    buf[(*pos)++] = '0';
    return;
  }
  
  while (value > 0) {
    tmp[i++] = hex_digits[value & 0xf];
    value >>= 4;
  }
  
  buf[(*pos)++] = '0';
  buf[(*pos)++] = 'x';
  
  while (i > 0) {
    buf[(*pos)++] = tmp[--i];
  }
}

static struct trace_ent entries[TRACE_SIZE];

int
main(int argc, char *argv[])
{
  int max = TRACE_SIZE;
  int count;
  int i;
  char buf[256];
  int pos;
  
  if (argc > 1) {
    max = atoi(argv[1]);
    if (max > TRACE_SIZE) max = TRACE_SIZE;
    if (max <= 0) max = TRACE_SIZE;
  }
  
  count = schedtrace(entries, max);
  
  if (count < 0) {
    printf(1, "schedtrace: failed\n");
    exit();
  }
  
  for (i = 0; i < count; i++) {
    pos = 0;
    append_hex(buf, &pos, entries[i].tlo);
    buf[pos++] = ' ';
    append_hex(buf, &pos, entries[i].thi);
    buf[pos++] = ' ';
    append_int(buf, &pos, entries[i].cpu);
    buf[pos++] = ' ';
    append_int(buf, &pos, entries[i].pid);
    buf[pos++] = ' ';
    append_int(buf, &pos, entries[i].ev);
    buf[pos++] = ' ';
    append_int(buf, &pos, entries[i].arg);
    buf[pos++] = ' ';
    append_int(buf, &pos, entries[i].seq);
    buf[pos++] = '\n';
    buf[pos] = '\0';
    write(1, buf, pos);
  }
  
  exit();
}
