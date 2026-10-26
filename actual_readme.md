# CAT2 VM implementation spec

## Purpose and source of truth

Extend the supplied Python 3 CAT2 assembler and virtual machine through Parts 1–4. This file is an implementation guide for an AI coding agent. Follow the course handout for grading requirements; use `instructions.md` for its shared overview and Part 1 checklist. Where those sources leave a design choice open, choose a consistent behavior, document it, and demonstrate it with a benchmark. Do not treat an existing TODO, placeholder counter, or successful run of the scalar program as proof that a feature is complete.

## Repository map

| File | Role |
| --- | --- |
| `cat2.py` | Shared architecture constants, field masks, register positions, ISA metadata, pipeline and memory timing assumptions. |
| `assembler.py` | Two-pass assembler; resolves labels and emits the `a.out` load image. |
| `execute.py` | VM, memory and register state, instruction execution, dumps, and implementation points. |
| `in.asm` | Supplied scalar array-sum benchmark. |
| `part1_store.asm` | Part 1 Store/load benchmark with expected values and counts. |
| `vecsum.asm` | Incomplete Part 4 benchmark template. |
| `instructions.md` | Short overview and Part 1 requirements. |

Part 1 Store and baseline counters are implemented in `execute.py`. The pipeline, cache, and vector behavior remains to be built.

## Architecture and compatibility rules

- Use Python 3 and extend the supplied files.
- Keep fundamental word, register, opcode, and memory sizes in `cat2.py`. Derive masks and field positions there; do not duplicate conflicting constants in the assembler or VM.
- Current defaults are `WORDSIZE = 31`, `NUMREGBITS = 3`, `OPCODESIZE = 7`, and `MEMLOADSIZE = 1024`. These are defaults, not independent values to copy into other files.
- Model the five pipeline stages as IF, ID, EX, MEM, WB. For Part 2, assume no forwarding: a consumer waits until the producer's result is available from WB under the chosen register-read/write timing convention.
- Preserve the existing scalar ISA, `sys` alias, assembler syntax, and ability to run `in.asm` while extending the machine.
- Support dumps of registers, memory, and the metadata needed to inspect counters, pipeline hazards, predictor state, and caches.
- Use additional CAT2 benchmark programs as needed to show correctness and performance.

## Part 1: Store and baseline measurements

1. Implement `st` so it writes the selected register value to the addressed data-memory word, applying the configured word mask and the same data-segment address checks used by loads. Account for indirect register operands through the existing operand-read path.
2. Count dynamically executed instructions, elapsed VM clock cycles, instruction-memory references, and data-memory references. A data load and a data store each count as a data reference; indirect operand reads also access data memory. Define whether initialization and diagnostic dumps are excluded from runtime counts, and keep that rule consistent.
3. Make the counter and memory dumps useful for checking a run. Keep the Part 1 baseline timing rule explicit so later pipeline and cache timing can be compared against it.
4. Add a small benchmark that stores a value, loads that address afterward, and makes the memory value and loaded register visible.

The current Part 1 implementation uses five non-overlapped cycles per decoded instruction and starts the clock at zero. `python3 assembler.py part1_store.asm` followed by `python3 execute.py --dump-memory` shows the benchmark's register, memory, and counter results. The benchmark comments give the expected values.

## Part 2: Hazards and prediction

1. Implement a five-stage pipeline timing model with a scoreboard or equivalent dependency tracker. Identify read-after-write dependencies for the source registers each instruction actually reads, including registers used for indirect addressing. Calculate and apply the required stall cycles with no forwarding.
2. Handle control flow for conditional branches and other instructions that change the instruction pointer. Apply and report the chosen stall or flush behavior.
3. Implement a one-bit predictor for conditional branches. Show the predictor entry/state, predicted outcome, actual outcome, and whether each prediction was wrong; update the state after resolution.
4. For each relevant hazard, report the instruction address or source location, the dependency or control cause, the scoreboard state, and the number of cycles stalled. Include stalls and flushes in the clock count.
5. State any timing convention the handout does not settle, such as whether ID may read a register in the same cycle its producer reaches WB. Use that convention consistently in traces and totals.

## Part 3: L1 caches

Implement RAM-backed L1 caches and run **every** required configuration:

| Organization | Instruction side | Data side |
| --- | --- | --- |
| Direct mapped, unified | 2 words × 4 lines | Shared |
| Direct mapped, unified | 4 words × 4 lines | Shared |
| Direct mapped, unified | 2 words × 8 lines | Shared |
| Split instruction/data | 2 words × 2 lines | 2 words × 2 lines |
| Split instruction/data | 4 words × 2 lines | 4 words × 4 lines |
| Two-way set associative, unified | 2 words × 8 total lines | Shared |

- Implement address breakdown, tags, valid state, hits, misses, block fills, data storage, and replacement where a set has multiple ways. A simple L2 of 8 words × 8 lines is optional.
- Route instruction fetches and data loads/stores through the selected cache organization. Use write-through plus write-allocate. The timing model may assume an ideal write buffer.
- Use the stated latencies: L1 = 1 cycle, optional L2 = 4 cycles, main memory = 25 cycles. Explain how these access costs enter the total clock count; avoid counting one access twice.
- For each configuration, report instruction and data references, hits, misses, hit rate, cache contents, and clock-cycle/performance impact. Show separate instruction/data statistics for split caches and clear combined totals for unified caches.
- Exercise the caches with the supplied scalar program and at least one benchmark large enough to produce meaningful hit and miss behavior.

## Part 4: Vector instructions

1. Add vector-add: element-by-element addition of two vectors. Add vector-sum: reduction of a vector to one result in one CAT2 instruction.
2. Define opcodes and operand encoding in the shared ISA metadata, then extend assembler validation, decoder, execution, and diagnostic output consistently. Document how base addresses, element count, destination, word overflow, and out-of-range memory are handled. The handout leaves these encoding choices open.
3. Include the vector instructions in the five-stage execution and timing model. Explain their latency, memory-reference accounting, and any effect on hazards or cache accesses.
4. Complete `vecsum.asm` as an executable benchmark that adds two 1 × N vectors with `N < 32`, then runs vector-sum. Show both the resulting vector and the reduction result.

## Agent workflow and acceptance checks

1. Inspect `cat2.py`, `assembler.py`, `execute.py`, and the benchmarks before editing. Keep ISA and architecture definitions shared; update all consumers together when changing an instruction format.
2. Implement one part at a time and run a benchmark after each part. Use focused checks for store/load visibility, instruction and data reference counts, RAW stall duration, branch predictor updates, every cache configuration, and vector results.
3. Compare pipeline and cache clock totals against the documented timing rules. Use memory and register dumps to verify results, not only printed counters.
4. Keep generated `a.out` images and output logs out of the source deliverable unless explicitly requested. Report the implementation choices and measurements needed to explain a demo.

## Basic commands

From this directory, with Python 3 available:

```sh
python3 assembler.py in.asm
python3 execute.py
```

The assembler writes `a.out` by default; the VM reads that file by default. These commands exercise the scalar baseline only. Assemble and run each added benchmark separately when verifying its feature.
