# CAT2 virtual machine

This repository contains the Python 3 CAT2 assembler, virtual machine, shared architecture definition, and benchmark programs.

See [actual_readme.md](actual_readme.md) for the detailed implementation spec and AI agent guidelines. Parts 1 and 2 are implemented; caches and vector instructions remain TODOs.

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

## Part 2: Pipeline hazards and branch prediction

- Use a scoreboard or equivalent mechanism to detect RAW dependencies in the five-stage IF/ID/EX/MEM/WB pipeline and calculate exact stalls with no forwarding.
- Handle branch and other control-flow hazards with stalls and flushes.
- Implement a one-bit predictor for conditional branches.
- Show each relevant hazard's instruction address or source location, cause, scoreboard contents, and stall duration.
- Show predictor state as branches execute, with predictions, actual outcomes, and mispredictions.

Run the Part 2 pipeline and its detailed trace:

```sh
python3 assembler.py part2_branches.asm
python3 execute.py --pipeline
```

This benchmark expects 8 executed instructions, 24 total cycles, 8 data-stall cycles, 4 control-stall cycles, and 2 mispredictions. Also run `part2_hazards.asm` for register and indirect-read hazards and `part2_control.asm` for call/return behavior. Replace the assembler input above to select a benchmark. Use `--no-trace` for final totals only, or `--dump-memory` to include memory contents.

Timing conventions and expected benchmark results are detailed in [actual_readme.md](actual_readme.md). Part 2 uses WB writes before ID reads, branch resolution at the end of EX, and an initially not-taken predictor.

Run the automated checks:

```sh
python3 -B -m unittest -v test_pipeline.py
```
