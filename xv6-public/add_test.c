#include "types.h"
#include "user.h"

int main(int argc, char* argv[]){
    int r;

    if(argc != 3){
        printf(2, "usage: add_test integer integer\n");
        exit();
    }

    r = add(atoi(argv[1]), atoi(argv[2]));
    printf(1, "%d\n", r);
    exit();
}