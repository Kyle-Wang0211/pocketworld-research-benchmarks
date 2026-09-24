#!/bin/bash
# sequential batch (timing-dependent budgets in the core => never run arms concurrently)
cd "$(dirname "$0")/.."
R=./tools/run_arm.sh
$R S_prod74_Xhost fix_S_prod74_Xhost
$R S_prod_A fix_S_prod_A
$R S_prod_Xhost fix_S_prod_Xhost
$R S_prod_Xdev fix_S_prod_Xdev
$R S_prod74_A_shuf fix_S_prod74_A_shuf
$R S_prod74_Xhost_shuf fix_S_prod74_Xhost_shuf
$R S_prod74_A_x110 fix_S_prod74_A_x110
$R S_prod74_Xhost_x110 fix_S_prod74_Xhost_x110
$R S_prod74_A off_S_prod74_A OFFICIAL_AETHER_DEVICE_ALIGN_V1=0
$R S_prod74_A fix_S_prod74_A_r2
$R S_deb74_A fix_S_deb74_A
$R S_deb74_Xhost fix_S_deb74_Xhost
$R S_deb_A fix_S_deb_A
$R S_deb_Xhost fix_S_deb_Xhost
$R S_deb74_A_x110 fix_S_deb74_A_x110
$R S_deb_A fix_S_deb_A_r2
$R S_deb74_A fix_S_deb74_A_r2
echo BATCH1_DONE
