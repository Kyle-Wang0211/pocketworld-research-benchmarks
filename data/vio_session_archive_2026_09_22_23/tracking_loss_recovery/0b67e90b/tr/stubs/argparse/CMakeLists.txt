# stub: 只为让 xrslam-pc/player 的 CMake 目标能被定义(我们从不构建它),避免 FetchContent 走 git。
cmake_minimum_required(VERSION 3.11)
project(argparse-stub LANGUAGES CXX)
add_library(argparse INTERFACE)
add_library(argparse::argparse ALIAS argparse)
