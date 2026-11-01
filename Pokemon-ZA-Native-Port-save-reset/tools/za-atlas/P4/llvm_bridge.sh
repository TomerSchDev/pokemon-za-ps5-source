#!/usr/bin/env bash
set -eu
# All WSL tool invocations go through this file, including paths with spaces.
case "$1" in
  symbolize)
    nice -n 10 llvm-symbolizer-21 --obj="$2" --output-style=JSON --inlines < "$3"
    ;;
  disassemble)
    nice -n 10 llvm-objdump-21 --disassemble --start-address="$3" --stop-address="$4" "$2"
    ;;
  *) exit 2 ;;
esac
