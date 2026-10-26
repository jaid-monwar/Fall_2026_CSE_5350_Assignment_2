## Overview
CAT2 is a small virtual machine used to explore processor organization and performance. The Python 3
starter package provides the basic CAT2 assembler/VM structure, memory and register model, a shared
architecture definition, and starter benchmark files. This file gives the shared architecture assumptions
and the detailed requirements for Part 1. The remaining parts are specified in the course handout.
Starter-code expectations: Use the supplied Python 3 starter files. Architecture parameters are
centralized in cat2.py; do not create separate, conflicting hard-coded word/register/opcode sizes in the
assembler and executor. If you want to use another programming language, discuss it with the
instructor/TA first.

## Architecture assumptions

- Use the classic 5-stage pipeline model: IF, ID, EX, MEM, WB.
- For Part 2 hazard analysis, assume no forwarding. Implement stalls based on when source operands
become available.
- The VM must be able to show (dump) register and memory contents and relevant metadata needed for
each part.
- Add or modify CAT2 benchmark programs as needed to demonstrate correctness and performance.

## Part 1 - Store and basic instrumentation

- Implement the CAT Store (st) instruction.
- Instrument the VM to report the number of instructions executed, total clock cycles, and total memory
references. Distinguish instruction and data references where appropriate.
- Use a benchmark to demonstrate that Store writes the correct value to memory and that subsequent loads observe the stored value.

### Part 1 implementation details

- The shared ISA in `cat2.py` already defines `st`, and `assembler.py` already assembles it. Implement its execution and the Part 1 measurements primarily in `execute.py`; keep architecture constants in `cat2.py`.
- For `st r, address`, read the source operand using the existing register/indirect-operand rules, write it to the data-segment-relative memory address, check the effective address as loads do, and mask the written value to the configured word width. An indirect source read is itself a data-memory reference.
- Count each dynamically executed instruction once, including the instruction that halts normal execution. Count every instruction fetch as an instruction-memory reference, even if the fetched instruction causes a trap. Count each data load, data store, and indirect operand read as one data-memory reference. Report instruction and data references separately and their sum as total memory references.
- Do not count loading the `a.out` image or printing diagnostic dumps as execution-time memory references. Initialize counters for each VM run and state clearly how exceptional termination affects the executed-instruction count.
- For Part 1, use a non-overlapped baseline of five cycles per dynamically executed instruction: one cycle each for IF, ID, EX, MEM, and WB. Start the cycle count at zero. This is a Part 1 measurement convention; later pipeline, hazard, and cache models must account for overlap, stalls, and memory latency separately.
- Add or modify a CAT2 benchmark that stores a known value, loads the same address afterward, and shows both the target memory word and the loaded register. The expected values and counts should be stated so the result can be checked.
