# CAT2 VM implementation spec

## Purpose and source of truth

Extend the supplied Python 3 CAT2 assembler and virtual machine through Parts 1–4. This file is an implementation guide for an AI coding agent. Follow the course handout for grading requirements; use `instructions.md` for its shared overview and Part 1 checklist. Where those sources leave a design choice open, choose a consistent behavior, document it, and demonstrate it with a benchmark. Do not treat an existing TODO, placeholder counter, or successful run of the scalar program as proof that a feature is complete.

## Repository map

| File | Role |
| --- | --- |
| `cat2.py` | Shared architecture constants, field masks, register positions, ISA metadata, pipeline and memory timing assumptions. |
| `assembler.py` | Two-pass assembler; resolves labels and emits the `a.out` load image. |
| `execute.py` | VM, memory and register state, instruction execution, dumps, and implementation points. |
| `pipeline.py` | Part 2 cycle simulation, scoreboard, interlocks, branch prediction, and traces. |
| `in.asm` | Supplied scalar array-sum benchmark. |
| `part1_store.asm` | Part 1 Store/load benchmark with expected values and counts. |
| `part2_hazards.asm` | Part 2 register, indirect operand, Store, and Load dependencies. |
| `part2_branches.asm` | One-bit predictor benchmark with taken, taken, not-taken outcomes. |
| `part2_control.asm` | Branch-and-link and return benchmark. |
| `test_pipeline.py` | Automated functional and cycle-count checks for Parts 1 and 2. |
| `vecsum.asm` | Incomplete Part 4 benchmark template. |
| `instructions.md` | Short overview and Part 1 requirements. |

Parts 1 and 2 are implemented. `execute.py` retains the Part 1 baseline and selects the Part 2 model in `pipeline.py` with `--pipeline`. Cache and vector behavior remains to be built.

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

### Implemented Part 2 timing conventions

- The pipeline has actual IF, ID, EX, MEM, and WB stage latches, issues in order, and starts at cycle 1 with the first fetch. The clock includes fill, drain, stalls, and flushes. Four independent instructions including the halt take eight cycles. The Part 1 baseline remains the default when `--pipeline` is omitted.
- WB writes the register file before ID reads it in the same cycle. There is no forwarding. A consumer immediately after a producer therefore waits two cycles; one intervening instruction reduces the wait to one cycle, and two intervening instructions eliminate it. A blocked ID freezes fetch and inserts a bubble into EX. The scoreboard lists each pending writer, its instruction address, stage, and WB availability cycle. Multiple writers to the same register are tracked.
- Dependencies use the actual source registers: arithmetic reads its old destination and its other operand; `st`, `bnz`, and `ret` read their operand; `ld` and `ldi` do not read their old destinations. Indirect operands also depend on their pointer register and `DATASEG`. Loads and Stores depend on `DATASEG`. A writer to `CODESEG` holds fetch until WB to prevent fetching with an obsolete segment base.
- Register and indirect operands are read in ID; arithmetic executes in EX; ordinary Load/Store memory accesses occur in MEM; register results commit in WB. Instruction fetch, MEM, and indirect ID reads use ideal independent memory access paths with one-cycle access, so cache and port contention add no latency in Part 2. After its pointer and segment registers are available, an indirect ID read waits only if an older EX Store will write the same effective address; MEM writes occur before ID reads in the same cycle. Address comparison does not access data memory. Store to a prefetched code word causes younger stale instructions to be squashed and replayed.
- The conditional predictor has one bit per physical branch address, initially not taken. The encoded branch target is available at IF; the prediction is captured with that fetched instruction. At the end of EX, the outcome updates the bit. If the predicted successor differs from the actual successor, ID and IF are flushed and fetching resumes at the correct address next cycle: a two-cycle control penalty. An outcome mismatch whose target equals fall-through needs no flush. Squashed instructions do not execute or change architectural state.
- `brl`, `ret`, and non-halting `int`/`sys` hold fetch from IF until resolution at the end of EX, adding two control cycles plus any separately counted RAW stalls. The halt (`sys 1 16`) stops further fetches and drains through WB. Its drain is already part of the pipeline completion time.
- Executed instruction count increases at EX and includes the halt and instructions that trap during execution; illegal opcodes do not count. Instruction references include successful speculative fetches subsequently squashed. Data references count actual ID and MEM accesses, including any reads repeated by code replay. Loader and diagnostic accesses are excluded. A speculative fetch fault is discarded if that instruction is flushed; an architectural illegal instruction stops fetch and drains older work. Every run resets scoreboard, predictor, counters, and stage latches.
- Each cycle prints the occupied stages and scoreboard. RAW events give the blocked instruction address, dependency, exact stall duration, and resume cycle. Branch events give captured prediction, actual outcome, misprediction status, flush/stall penalty, and updated predictor table. Each other control event reports its own control stall count, separate data wait count, and scoreboard, with a flag for code-segment serialization. The final summary distinguishes data stalls, control stalls, code-segment serialization stalls, code replay stalls, and fetched instructions squashed. `--no-trace` suppresses the detailed trace while retaining final totals; `--max-cycles` bounds a run (default 100000).

Run a Part 2 benchmark:

```sh
python3 assembler.py part2_branches.asm
python3 execute.py --pipeline
```

| Benchmark | Executed instructions | Total cycles | Data stalls | Control stalls | Expected result |
| --- | --- | --- | --- | --- | --- |
| `part2_hazards.asm` | 8 | 20 | 8 | 0 | r1 = 6, r2 = 7, r4 = 13, memory[9] = 7 |
| `part2_branches.asm` | 8 | 24 | 8 | 4 | r1 = 0; predictions N,T,T; outcomes T,T,N; two mispredictions |
| `part2_control.asm` | 5 | 13 | 0 | 4 | r1 = 1, r5 = 2 after call/return |

Run the automated checks with `python3 -B -m unittest -v test_pipeline.py`.

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
