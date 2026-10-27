# Part 2 implementation analysis

Reviewed against Part 2 on page 1 of [CAT2_Programming_Assignment_Fall_2026.pdf](CAT2_Programming_Assignment_Fall_2026.pdf).

**Part 2 is substantially implemented, but the review found one reproducible stall-count issue and one smaller reporting gap.** None of its six required features is entirely missing.

| Requirement | Assessment |
| --- | --- |
| Five-stage pipeline with scoreboard | Implemented |
| RAW detection and exact stalls without forwarding | Register dependencies work; unnecessary memory stalls occur |
| Control-hazard stalls/flushes | Implemented and passed checks |
| One-bit conditional branch predictor | Implemented and passed checks |
| Hazard location, cause, scoreboard, stall count | Detailed RAW reporting; control-event counts need improvement |
| Predictor state, outcomes, mispredictions | Implemented |

## 1. Unnecessary stalls inflate RAW and total cycle counts

In `pipeline.py`, lines 153–154, an indirect operand read stalls whenever an older Store occupies EX. The code does **not check whether their memory addresses match**:

```python
indirect = any(field & INDIRECT_BIT for field in self.operand_fields(instruction))
memory_wait = indirect and self.ex is not None and self.ex.opcode == 8
```

The following program reproduces the issue:

```asm
go 0
ldi 1 42
ldi 3 101
ldi 4 0
st 1 100
add 2 *3
sys 1 16
100 dw 0
101 dw 7
end
```

The Store writes address **100**, while `add` reads address **101**. All required registers are available when the `add` reaches ID, so there is no RAW dependency between these instructions.

Nevertheless, the implementation reports one RAW stall and **11 cycles**. Under its documented timing and independent memory paths, these six instructions require **10 cycles**: six executed instructions plus four cycles for pipeline fill and drain.

The observed hazard event occurs at cycle 6 for the instruction at address 4. It reports an empty register-dependency map, `memory='older Store before indirect read'`, and `stall_cycles=1`.

The final values are correct: r1 is 42, r2 is 7, and memory[100] is 42. The issue concerns the PDF's requirement to determine the **exact number of required stall cycles**, rather than architectural result correctness.

This conservative interlock is documented in the implementation notes, but documentation does not eliminate the unnecessary stall. Checking effective addresses, once the required pointer and segment registers are available, would allow unrelated memory accesses to proceed while preserving the interlock for accesses to the same address.

## 2. Individual control hazards do not explicitly report stall counts

In `pipeline.py`, lines 228–229, call/return/system-control events print the instruction address, target, and reason, but omit a per-event stall count:

```python
self.emit("CONTROL", pc=instruction.address, target=redirect,
          reason="fetch held until end of EX")
```

For example, `part2_control.asm` reports **four total control stalls**, without explicitly stating that the call and return each contributed two.

The per-cycle trace includes the scoreboard and allows the individual penalties to be reconstructed. This is therefore a reporting weakness rather than an execution failure. Adding a per-event `stall_cycles` field, and clearly separating control waits from any RAW waits, would make compliance with the PDF's hazard-reporting requirement clearer.

## Verification performed

- All **14 existing tests passed** using `python3 -B -m unittest -v test_pipeline.py`.
- The three Part 2 benchmarks produced their documented totals:

  | Benchmark | Executed instructions | Total cycles | Data stalls | Control stalls | Mispredictions |
  | --- | --- | --- | --- | --- | --- |
  | `part2_hazards.asm` | 8 | 20 | 8 | 0 | 0 |
  | `part2_branches.asm` | 8 | 24 | 8 | 4 | 2 |
  | `part2_control.asm` | 5 | 13 | 0 | 4 | 0 |

- **1,500 additional deterministic generated programs** matched the sequential VM's registers, memory, and executed-instruction counts. Their pipeline cycle totals also matched the implementation's accounting formula. These comparisons support functional consistency; they do not independently establish that every reported stall is necessary, as the non-aliasing reproduction above demonstrates.
- Additional checks for indirect branches, returns, load-use dependencies, segment-register behavior, and branches whose target equals fall-through passed.

The generated review cases used temporary files and were not added to the repository's test suite.

## Running Part 2

Part 2 requires `--pipeline`; the default execution mode remains the Part 1 baseline. For example:

```sh
python3 assembler.py part2_branches.asm
python3 execute.py --pipeline
```

The implementation was not modified during this review.
