# CAT2 virtual machine

This repository contains the Python 3 CAT2 assembler, virtual machine, shared architecture definition, and benchmark programs.

See [actual_readme.md](actual_readme.md) for the detailed implementation spec and AI agent guidelines. Part 1 Store and baseline counters are implemented; pipeline hazards, caches, and vector instructions remain TODOs.

## Run the scalar baseline

```sh
python3 assembler.py in.asm
python3 execute.py
```

The assembler writes `a.out`; the VM reads it by default. The scalar baseline does not demonstrate that Parts 1–4 are complete.

## Run the Part 1 Store check

```sh
python3 assembler.py part1_store.asm
python3 execute.py --dump-memory
```

The benchmark expects memory word 4 and registers 1 and 2 to contain `42`. Its expected counters are written in `part1_store.asm`.
