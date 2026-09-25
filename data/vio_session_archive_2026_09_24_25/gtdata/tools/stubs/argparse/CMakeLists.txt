cmake_minimum_required(VERSION 3.10)
project(argparse_stub)
add_library(argparse INTERFACE)
add_library(argparse::argparse ALIAS argparse)
