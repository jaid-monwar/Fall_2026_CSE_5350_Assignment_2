# Part 2 implementation choices and explanations

## 1. What Part 2 adds

Part 2 adds a working, cycle-by-cycle IF/ID/EX/MEM/WB pipeline to the CAT2 VM. It detects read-after-write (RAW) dependencies, holds consumers until their operands are available without forwarding, handles changes in control flow, and predicts conditional branches with one bit per branch address. Its output exposes the stage occupants, scoreboard, stall durations, predictor changes, and final counters.

The implementation follows the requirements in `actual_readme.md`. The requirements specify five stages and no forwarding, but leave several timing details open. Choices such as same-cycle WB/ID access, EX branch resolution, and predictor initialization are documented below as implementation conventions. They are needed to make exact cycle totals reproducible.

## 2. Files changed or added

| File | Change | Reason |
| --- | --- | --- |
| `pipeline.py` | Added `Instruction` and `Pipeline`, including the stage loop, scoreboard, predictor, and trace events. | Gives the overlapping pipeline its own state and timing while reusing the VM's registers, memory, checks, and reference counters. |
| `execute.py` | Added pipeline selection, command-line controls, and the shared `finish_run()` reporting function. | Lets both execution models produce the same register/memory/counter format and keeps Part 1 reproducible. |
| `cat2.py` | Added explicit register-file timing, branch-resolution, and initial prediction settings. | Keeps the chosen architectural conventions visible beside the existing stage and forwarding settings. |
| `part2_hazards.asm` | Added a program with direct, indirect, Store, and Load dependencies. | Makes four two-cycle RAW stalls and their functional results easy to verify. |
| `part2_branches.asm` | Added a three-iteration conditional loop. | Demonstrates predictor learning, a correct taken prediction, and the exit misprediction. |
| `part2_control.asm` | Added a branch-and-link/return program. | Verifies link-register behavior and control stalls outside conditional prediction. |
| `test_pipeline.py` | Added 18 automated test methods, several with multiple cases. | Checks numerical timing expectations and architectural results, including regressions against Part 1, address-aware interlocks, and individual control penalties. |
| `README.md`, `actual_readme.md` | Updated status, run commands, expected results, and conventions. | Makes the implemented mode and its assumptions discoverable. |

Completed code markers use `PART 2 TODO (ADDRESSED)`, preserving the TODO locations while indicating that their work is implemented. The assembler already supports the scalar instructions needed here; Part 2 does not require new opcodes or assembly syntax.

## 3. Keeping the Part 1 baseline available

`execute.py` selects the pipeline only when `--pipeline` is supplied. Without that flag, the Part 1 interpreter still uses its documented baseline of five cycles per executed instruction.

This preserves a useful comparison: the same benchmark can run through both models, with identical final register and memory values but different cycle totals. It also avoids making the earlier Part 1 benchmark's expected 20 cycles silently change when run with the original command.

`run_vm()` resets architectural state and loads the image before selecting either model. For a pipeline run, it creates a fresh `Pipeline` instance. That instance owns the stage latches, predictor, dynamic instruction sequence numbers, events, and timeline, so those values cannot leak into a subsequent run. `finish_run()` prints architectural results and returns the shared counters; pipeline results additionally contain a `pipeline` dictionary with timing statistics, predictor state, events, and the cycle timeline.

## 4. How the five stages are represented

Each fetched instruction receives an `Instruction` record. It contains the decoded fields, its destination, captured operands, eventual result, and prediction information. It also records both the logical PC and physical instruction address:

```text
physical instruction address = logical PC + reg[CODESEG]
```

A dynamic sequence number distinguishes repeated executions of the same static instruction. For example, `2:bnz#8` identifies physical address 2, mnemonic `bnz`, and dynamic fetch number 8. Sequence numbers can have gaps among executed instructions because speculative fetches may be flushed.

The persistent latches are `id`, `ex`, `mem`, and `wb`. IF is the instruction fetched during the current cycle; it enters the ID latch for the following cycle. This represents all five stages without retaining a redundant IF latch after the cycle ends.

| Stage | Implemented responsibility | Why this placement matters |
| --- | --- | --- |
| IF | Read an instruction, extract its fields for fetch control, and choose the predicted successor. | Allows younger instructions to be fetched before a conditional branch resolves. |
| ID | Validate the instruction, check dependencies, and capture register/indirect operands. | Prevents a consumer from reading an unavailable value. |
| EX | Perform arithmetic, resolve control flow, update branch prediction, and count the executed instruction. | Gives branch recovery a defined point and keeps flushed ID/IF instructions out of the execution count. |
| MEM | Read an ordinary `ld` value or perform an ordinary `st` write. | Preserves the Load/Store stage of the required model. |
| WB | Commit the register result. | Defines when a dependent instruction can obtain that result without forwarding. |

Stage occupants move at the end of each simulated cycle. Processing WB before ID within a cycle implements the chosen register-file convention. MEM writes also precede indirect ID reads in that cycle. Although Python evaluates EX before IF, a redirect is applied after the current cycle's fetch handling to model resolution at the end of EX.

## 5. Register timing and exact RAW stalls

### WB writes before ID reads

The register file is written during WB before ID reads it in the same cycle. A consumer may therefore read a producer's result in the producer's WB cycle. There is no EX-to-ID or MEM-to-ID forwarding; the consumer waits for the register write.

This convention was chosen because it is a simple, explicit way to define same-cycle register access. The specification requires no forwarding but does not state whether a read in the WB cycle succeeds. Choosing the opposite convention would add a cycle to some dependency stalls, so the convention must accompany the reported measurements.

For two adjacent instructions such as `ldi 1 5` followed by `inc 1`:

| Cycle | `ldi 1 5` | `inc 1` | Explanation |
| --- | --- | --- | --- |
| 1 | IF | — | Fetch the producer. |
| 2 | ID | IF | Fetch the consumer. |
| 3 | EX | ID, stalled | The value is not yet in the register file. |
| 4 | MEM | ID, stalled | The consumer still waits for WB. |
| 5 | WB | ID, reads | WB writes first; ID can now capture the value. |
| 6 | — | EX | The consumer executes using its captured operand. |
| 7 | — | MEM | The consumer advances. |
| 8 | — | WB | The consumer commits its result. |

The consumer incurs exactly two stall cycles. With one independent instruction between producer and consumer, the consumer initially reaches ID one cycle later and stalls once. With two independent instructions between them, ID coincides with WB and no stall is needed. These counts assume that other hazards have not already changed the relative timing.

### Scoreboard contents and calculation

`scoreboard()` constructs a register-to-pending-writers mapping from the current EX and MEM occupants. An EX writer is available two cycles later; a MEM writer is available one cycle later. The current WB writer is excluded because its result has already committed before ID checks the table.

Each pending-writer entry includes its instruction address, dynamic sequence number, stage, and availability cycle. Multiple pending writers to the same register are retained. A later consumer must wait for the newest required value, so using only the first writer could release the consumer too early.

At ID cycle `c`, the register wait is calculated as:

```text
register wait = max(0, latest required WB cycle - c)
```

If several sources are unavailable, their waits overlap. The duration is the maximum wait, rather than the sum of the waits. For example, sources becoming available in one and two cycles require two stall cycles overall.

During a stall, ID retains the consumer, fetch is frozen, and a bubble enters EX. Older EX/MEM/WB instructions continue advancing so that the dependency can clear. `data_stalls` increases once per held cycle. The first RAW event for the blocked instruction reports the dependency, scoreboard snapshot, exact duration, and resume-ID cycle; the cycle trace shows its continued progress without repeating the same hazard announcement every cycle.

## 6. Checking the sources each instruction actually uses

Treating every encoded register field as a source would create false hazards. For example, `ldi 1 5` writes r1 but does not read its previous value. Conversely, ignoring a pointer or segment register could let an instruction use an obsolete address.

`operand_fields()`, `sources()`, and `destination()` separate these roles:

| Instruction | Sources relevant to dependency detection | Register destination |
| --- | --- | --- |
| `add`, `sub` | Old first operand and second operand; an indirect operand also uses its pointer and `DATASEG`. | First register. |
| `inc`, `dec` | Old first operand. | First register. |
| `ld` | `DATASEG`; the destination's old value is unused. | First register. |
| `st` | Stored operand and `DATASEG`; an indirect source also reads through its pointer. | None. |
| `ldi` | None. | First register. |
| `bnz` | Condition operand, including pointer/segment dependencies if indirect. | None. |
| `brl` | No register source for its encoded target. | Encoded link register. |
| `ret` | Return-address operand, including indirect dependencies if used. | None. |
| Non-halting `int`/`sys` | Uses the encoded trap number and target under the existing VM semantics. | `TRAPREGLINK` when a return link is produced. |
| `sys 1 16` | The encoded halt operation does not read r1's value. | None. |

The assembler's existing restrictions on writable destinations still apply. The pipeline also rejects an encoded indirect register destination rather than writing outside the physical register file.

No additional WAR or WAW scheduling mechanism is needed in this model: instructions capture operands in order, execute in order, and commit register results in order. Multiple writers are still recorded because a later RAW consumer must wait for all relevant older writes.

## 7. Indirect memory operands and segment registers

CAT2 permits memory reads through indirect register operands, such as `add 2 *3`. The pipeline retains that behavior by reading indirect operands during ID. Ordinary `ld` and `st` still use MEM. This choice preserves the starter's operand semantics without introducing extra pipeline stages or new opcodes.

An indirect ID read can otherwise overtake an older Store that is still in EX. The interlock now compares their effective memory addresses and waits only when they match. For a matching address, ID waits one cycle for that Store to reach MEM; MEM performs the write before ID reads in the same cycle. An unrelated address needs no memory stall under the independent access paths used in this model.

The comparison uses:

```text
Store address         = captured Store offset + reg[DATASEG]
indirect read address = reg[physical pointer register] + reg[DATASEG]
```

Pointer and segment values are compared only after the scoreboard confirms that all source registers for the ID instruction are available. If a source is still pending, the instruction waits for its register dependency first. By the next cycle an older EX Store has advanced to MEM and writes before any permitted ID read. This avoids using stale pointer values or counting overlapping register and memory waits twice.

Address comparison uses register values and the Store's captured offset; it does not dereference either address. Actual reads and writes still go through the existing checked VM memory functions, so comparison does not inflate `Datarefs`. A matching-address RAW event includes `memory_address` and a reason identifying the older Store's pending write.

For example, with all operands ready, the following six-instruction program takes 10 cycles with no data stalls:

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

Store writes address 100 while the indirect read accesses address 101. The final r2 is 7 and memory[100] is 42. Changing the pointer initialization to `ldi 3 100` creates a real memory dependency: the program takes 11 cycles with one data stall, and r2 reads the newly stored 42. Both versions make exactly two data-memory references. Regression cases also use a nonzero `DATASEG` to verify that the comparison uses effective addresses.

`DATASEG` is an implicit source for ordinary loads, Stores, and indirect operands. The scoreboard therefore delays these instructions until an older `DATASEG` write has committed. Fetch depends on `CODESEG`; a fetched instruction that writes `CODESEG` blocks later fetches until its WB stage. This avoids fetching with the previous code-segment base. Those blocked cycles are reported separately as `serialization_stalls`.

Part 2 assumes ideal independent instruction-fetch, MEM, and indirect-ID access paths with one-cycle memory accesses. It does not model contention between those paths. This keeps the measurements focused on the required data and control hazards; cache latencies and cache behavior belong to Part 3.

## 8. One-bit conditional branch prediction

`predictor` is a dictionary keyed by the branch's physical instruction address. Each entry stores one Boolean bit: false means predict not taken; true means predict taken. An absent entry predicts not taken. This models an independent bit for each observed branch, without a finite table's indexing collisions or replacement policy, which the supplied requirements do not specify.

At IF, `bnz` captures the current prediction in its instruction record. A taken prediction selects the encoded target; a not-taken prediction selects `pc + 1`. The target is assumed available from the fetched instruction in IF. At EX, the captured condition determines the actual outcome, and the table bit is replaced with that outcome.

Saving the prediction with the instruction is essential: the prediction being evaluated is the one used when that dynamic instruction was fetched. Looking up the table again at EX could observe a newer update and misreport whether the earlier prediction was correct.

Every executed conditional branch reports its address, captured prediction, actual outcome, predicted and actual successors, misprediction status, flush penalty, and updated table. A flushed branch never reaches EX and therefore does not update the predictor or branch-execution count.

For `part2_branches.asm`, the branch at address 2 observes:

| Execution | Bit used at fetch | Prediction | Actual outcome | Updated bit | Recovery |
| --- | --- | --- | --- | --- | --- |
| First | 0 | Not taken | Taken | 1 | Flush and redirect. |
| Second | 1 | Taken | Taken | 1 | Continue the predicted path. |
| Third | 1 | Taken | Not taken | 0 | Flush and redirect to loop exit. |

This explains the expected two mispredictions: the first encounter learns the taken behavior, and the loop exit reverses it.

## 9. Why a conditional redirect costs two cycles

A conditional branch resolves at the end of EX. At that time, younger work may occupy ID and IF. If the predicted successor differs from the actual successor, those two slots are flushed and the correct successor is fetched next cycle. This produces a two-cycle control penalty.

Flush handling prevents the discarded ID instruction from reading operands or advancing to EX. A current-cycle speculative IF fetch may still occur and is included in instruction-reference accounting. The flush clears fetch blocks associated with discarded instructions, including a halt encountered on the wrong path, so a speculative halt cannot prevent execution of the correct path.

The implementation distinguishes an incorrect direction prediction from an incorrect successor address. If a taken target happens to equal fall-through, the direction prediction can be wrong while the selected successor is correct. That case increments `mispredictions` but needs no flush or control-cycle penalty.

## 10. Other control flow and stopping execution

The one-bit predictor applies to conditional `bnz` instructions. `brl`, `ret`, and non-halting `int`/`sys` hold fetch until their target resolves at the end of EX. A control instruction fetched in cycle `f` normally occupies ID in `f + 1` and EX in `f + 2`; those are two blocked fetch cycles. Any RAW stalls needed by the control instruction are counted separately, avoiding counting one held cycle as both a data and a control stall.

Each instruction now retains its own `data_stall_cycles` and `control_stall_cycles`. Its `CONTROL` event is emitted after the current EX cycle's fetch hold has been counted. This timing matters: emitting before that update would report only the earlier ID hold and omit the final control cycle. The event includes:

| Field | Meaning |
| --- | --- |
| `pc`, `target`, `reason` | Location, resolved successor, and explanation for the fetch hold. |
| `stall_cycles` | This instruction's contribution to the global control-stall total. Normally 2 for a call, return, or non-halting system control. |
| `data_stall_cycles` | Its separate ID dependency waits; these cycles are already included in the global data-stall total. |
| `code_segment_wait` | Whether this instruction also writes `CODESEG`, so its fetch hold is classified under code-segment serialization instead of ordinary control stalls. |
| `scoreboard` | Pending-writer state in the resolution cycle. |

For `part2_control.asm`, the call and return each report `stall_cycles=2` and `data_stall_cycles=0`, accounting explicitly for the total of four control cycles. A return immediately after a producer of its link register reports two control cycles and two data cycles separately. Those waits must not be combined and then charged to both global categories.

The event uses measured per-instruction counts rather than always printing 2. For example, `brl` with `CODESEG` as its link destination is serialized until WB; its control event reports `stall_cycles=0` and `code_segment_wait=True`, while the final `serialization_stalls` total records that hold. Conditional `BRANCH` events also expose `stall_cycles`, equal to their existing `flush_cycles`, so their individual penalties are explicit too.

`brl` produces the logical return PC, `pc + 1`, for its encoded link register. `ret` obtains its target from the operand captured in ID. Non-halting system control retains the existing CAT2 link/target behavior; Part 2 does not introduce a new operating-system call model.

The halt operation blocks further fetches, reaches EX, and then drains through MEM and WB. Earlier instructions can therefore finish before final state is reported. The drain is already included in the pipeline's completion time and is not charged again as an extra control penalty.

## 11. Preserving Store behavior when code is modified

CAT2 code and data share the same RAM. A Store can therefore change a word that a younger instruction has already fetched. Executing the saved old word would disagree with the sequential VM's behavior.

When Store writes in MEM, the pipeline checks younger EX and ID instruction addresses. If either matches the modified word, it discards the stale instruction and younger work, then fetches the affected logical PC again. An EX replay loses three cycles relative to that instruction's original IF position; an ID replay loses two. These costs are recorded as `replay_stalls`, separate from branch penalties.

The replay prevents an affected EX instruction from executing before it is discarded. Tests overwrite a prefetched `ldi` instruction and confirm that both models execute the replacement instruction and finish with identical architectural state. This behavior extends Store correctness to the overlap introduced in Part 2.

## 12. Counters, faults, and output

The total clock now comes from actual pipeline cycles. Each iteration of `Pipeline.run()` advances it by one, including idle slots, dependency waits, redirects, and final drain. For the supplied nonempty, normally terminating benchmarks, the totals can be checked as:

```text
cycles = executed instructions + 4
       + data stalls + control stalls
       + code-segment serialization stalls + code replay stalls
```

The four cycles account for filling and draining a five-stage pipeline. This is why four independent instructions take eight cycles rather than the Part 1 baseline's twenty.

| Measurement | Meaning in pipeline mode |
| --- | --- |
| `IC` | Instructions that reach EX, including halt and an instruction that traps during execution. Flushed instructions and illegal opcodes are excluded. |
| `Coderefs` | Successful instruction-memory reads, including speculative reads later flushed. |
| `Datarefs` | Actual indirect ID reads and ordinary MEM reads/writes; code replay can cause an operand read to be repeated. |
| `Totalrefs` | `Coderefs + Datarefs`. |
| `data_stalls` | Cycles ID is held by register or Store/indirect-read dependencies. |
| `control_stalls` | Conditional redirect penalties and fetch waits for other control instructions. |
| `serialization_stalls` | Additional fetch holds for a pending `CODESEG` write. |
| `replay_stalls` | Recovery cycles when Store changes a prefetched code word. |
| `branches`, `mispredictions` | Executed conditional branches and direction prediction mismatches. |
| `squashed` | Discarded stage entries during branch flushes or code replay. |

The branch benchmark executes 8 instructions but makes 11 instruction references: three successful speculative fetches are discarded. Such a difference is expected once prediction introduces speculative fetching. Image loading and diagnostic dumps remain excluded from runtime memory-reference counts.

An instruction-fetch address error is saved on the fetched record and considered at ID. If an older branch flushes that record first, the speculative fault does not terminate a valid program. Architectural illegal instructions stop fetch and allow older work to drain. Arithmetic overflow detected in EX suppresses that instruction's result and flushes younger work. Invalid architectural data-memory accesses and invalid destinations retain Python exceptions from the VM checks; this is not a complete hardware exception/interrupt subsystem.

The default trace prints physical addresses and mnemonics rather than reconstructing source lines, satisfying the requirement to locate hazards by instruction address. It includes the five stage occupants and scoreboard each cycle, plus `RAW`, `BRANCH`, `CONTROL`, `FLUSH`, `HALT`, `TRAP`, and `CODE_REPLAY` events when relevant. A typical RAW event identifies r1's producer in EX, its WB availability at cycle 5, a two-cycle wait starting at cycle 3, and ID resuming at cycle 5.

## 13. Benchmark results and why the totals are expected

| Benchmark | Executed instructions | Data stalls | Control stalls | Total cycles | Key result |
| --- | --- | --- | --- | --- | --- |
| `part2_hazards.asm` | 8 | 8 | 0 | 20 | r1 = 6, r2 = 7, r4 = 13, memory[9] = 7. |
| `part2_branches.asm` | 8 | 8 | 4 | 24 | r1 = 0; outcomes T,T,N; two mispredictions; final bit at address 2 is 0. |
| `part2_control.asm` | 5 | 0 | 4 | 13 | r1 = 1 and r5 = 2 after call/return. |
| `part1_store.asm`, pipeline mode | 4 | 2 | 0 | 10 | Memory[4] and r1/r2 remain 42. |

In the hazard benchmark, `ldi` to `inc`, pointer `ldi` to indirect `add`, `add` to `st`, and `ld` to `add` each require two RAW stalls. Thus `8 + 4 + 8 = 20`. Its data references are one indirect read, one Store, and one Load.

The branch benchmark executes one initialization, three decrement/branch pairs, and the final halt: `1 + 6 + 1 = 8`. The first decrement waits two cycles for initialization, and each of the three branches waits two cycles for its decrement: eight data stalls. The two redirects add four control cycles, so `8 + 4 + 8 + 4 = 24`.

The control benchmark executes initialization, call, function increment, return, and halt. The call and return each add two control cycles. No register dependency adds a stall in this layout, giving `5 + 4 + 4 = 13`.

## 14. Verification and use

Run the branch demonstration from the project directory:

```sh
python3 assembler.py part2_branches.asm
python3 execute.py --pipeline
```

Replace the assembler input with `part2_hazards.asm` or `part2_control.asm` to inspect the other cases. Useful options are:

- `--no-trace`: retain final totals while suppressing cycle and event output.
- `--dump-memory`: include the complete final memory dump.
- `--aout PATH`: select a particular assembled image.
- `--max-cycles N`: bound a pipeline run; the default is 100000 cycles, after which a `RuntimeError` identifies the limit.

Run the automated checks:

```sh
python3 -B -m unittest -v test_pipeline.py
```

All 18 test methods pass. Their cases check independent-instruction overlap and halt drain; RAW waits with zero, one, or two intervening instructions; multiple pending writers; Part 1 Store equivalence; indirect pointer and ordinary Load dependencies; Store-to-indirect-read ordering; `DATASEG` and `CODESEG` handling; predictor learning and reset across runs; correct not-taken prediction; discarded Store/illegal instructions on a wrong path; call/return and system control; the supplied scalar sum's unchanged result of 113; and replay after code modification.

The added regression cases verify that different effective memory addresses introduce no memory stall, matching addresses retain the required one-cycle interlock, pointer dependencies are resolved before comparison, and the address check adds no memory references. They compare registers and memory against the sequential model. Reporting checks verify two cycles per ordinary control event, keep a return's RAW waits separate, preserve the code-segment serialization category, and verify conditional penalties of 2, 0, and 2 for the branch benchmark. Existing benchmark totals remain 20 cycles for `part2_hazards.asm`, 24 for `part2_branches.asm`, and 13 for `part2_control.asm`.

These checks validate the implemented conventions and expected benchmark behavior. They do not establish that another permitted timing convention would produce identical cycle counts. In particular, cache delays, memory-port contention, a finite aliased predictor table, and forwarding are outside this Part 2 model.
