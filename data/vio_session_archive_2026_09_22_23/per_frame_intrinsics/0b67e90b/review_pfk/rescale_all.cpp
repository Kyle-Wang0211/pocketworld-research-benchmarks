#include <cstdio>
#include <cstring>
#include <cstdint>
#include "PwXrslamTransportCore.h"
int main(int, char**argv){ FILE*f=fopen(argv[1],"r"); double r[4],e[4]; int n=0,bad=0;
 while(fscanf(f,"%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf",&r[0],&r[1],&r[2],&r[3],&e[0],&e[1],&e[2],&e[3])==8){
  double g[4]; PWXrslamTransportScaleIntrinsicsForBoxNxN(r,3,g); ++n;
  if(memcmp(g,e,sizeof g)) ++bad; }
 printf("rows=%d bitwise_mismatch=%d\n",n,bad); }
