"""Cycle-by-cycle CAT2 IF/ID/EX/MEM/WB model, with no forwarding.

WB writes before ID reads. Branches resolve at the end of EX, so a wrong
conditional prediction squashes ID and IF. Indirect operand memory reads occur
in ID; ordinary LD/ST access memory in MEM.
"""

from dataclasses import dataclass

from cat2 import (
    ADDMASK, BRANCH_PREDICTOR_INITIAL, BRANCH_RESOLVE_STAGE, CODESEG, DATASEG,
    FORWARDING, INDIRECT_BIT, PIPELINE_STAGES, REGISTER_WRITE_BEFORE_READ,
    NUMMASK, NUMREGS, OPCPOSITION, REG1POSITION, REG2POSITION, REGMASK,
    TRAPREGLINK, physical_register,
)


@dataclass
class Instruction:
    sequence: int
    pc: int
    address: int
    opcode: int
    r1: int
    r2: int
    immediate: int
    destination: object = None
    prediction: bool = False
    predicted_pc: int = 0
    operand1: int = 0
    operand2: int = 0
    result: object = None
    fetch_error: object = None
    reported_hazard: bool = False
    data_stall_cycles: int = 0
    control_stall_cycles: int = 0


class Pipeline:
    """Execute in order with real stage latches and speculative instruction fetches."""

    def __init__(self, vm, trace=True):
        if (FORWARDING or not REGISTER_WRITE_BEFORE_READ or BRANCH_RESOLVE_STAGE != "EX"
                or PIPELINE_STAGES != ("IF", "ID", "EX", "MEM", "WB")):
            raise ValueError("This model requires IF/ID/EX/MEM/WB, no forwarding, "
                             "WB before ID reads, and EX branch resolution")
        self.vm = vm
        self.trace = trace
        self.id = self.ex = self.mem = self.wb = None
        self.next_pc = 0
        self.sequence = 0
        self.fetch_block = None
        self.stop_fetch = False
        self.fault = None
        self.predictor = {}
        self.events = []
        self.timeline = []
        self.stats = dict(data_stalls=0, control_stalls=0, serialization_stalls=0, replay_stalls=0,
                          branches=0, mispredictions=0, squashed=0)

    def emit(self, kind, **details):
        event = dict(kind=kind, cycle=self.vm.clock, **details)
        self.events.append(event)
        if self.trace:
            print(f"[{kind}] cycle={self.vm.clock} " +
                  " ".join(f"{key}={value}" for key, value in details.items()))

    def label(self, instruction):
        if instruction is None:
            return "-"
        name = self.vm.opcodes.get(instruction.opcode, (None, "illegal"))[1]
        return f"{instruction.address}:{name}#{instruction.sequence}"

    @staticmethod
    def destination(opcode, r1):
        if opcode in (1, 2, 3, 4, 7, 9, 13):
            return r1
        if opcode == 16 and r1 != 1:
            return TRAPREGLINK
        return None

    @staticmethod
    def operand_fields(instruction):
        if instruction.opcode in (1, 2):
            return (instruction.r1, instruction.r2)
        if instruction.opcode in (3, 4, 8, 12, 14):
            return (instruction.r1,)
        return ()

    def sources(self, instruction):
        registers = set()
        for field in self.operand_fields(instruction):
            registers.add(physical_register(field))
            if field & INDIRECT_BIT:
                registers.add(DATASEG)
        if instruction.opcode in (7, 8):
            registers.add(DATASEG)
        return registers

    def scoreboard(self):
        board = {}
        # WB has already committed this cycle. EX/MEM cannot stall downstream.
        for stage, instruction, remaining in (("EX", self.ex, 2),
                                               ("MEM", self.mem, 1)):
            if instruction is not None and instruction.destination is not None:
                board.setdefault(instruction.destination, []).append(dict(
                    pc=instruction.address, sequence=instruction.sequence,
                    stage=stage, available=self.vm.clock + remaining))
        return board

    def fetch(self):
        pc = self.next_pc
        address = pc + self.vm.reg[CODESEG]
        error = None
        try:
            word = self.vm.getcodemem(pc)
        except IndexError as exc:
            # A fault on a speculative path must not terminate a valid branch.
            word = 0
            error = str(exc)
        opcode = word >> OPCPOSITION
        r1 = (word >> REG1POSITION) & REGMASK
        r2 = (word >> REG2POSITION) & REGMASK
        immediate = word & ADDMASK
        self.sequence += 1
        instruction = Instruction(self.sequence, pc, address, opcode, r1, r2,
                                  immediate, self.destination(opcode, r1),
                                  fetch_error=error)
        instruction.predicted_pc = pc + 1
        if opcode == 12:
            instruction.prediction = self.predictor.get(address, BRANCH_PREDICTOR_INITIAL)
            if instruction.prediction:
                instruction.predicted_pc = immediate
        self.next_pc = instruction.predicted_pc
        if error is not None or opcode not in self.vm.opcodes:
            self.fetch_block = (instruction.sequence, "fault")
        elif instruction.destination == CODESEG:
            self.fetch_block = (instruction.sequence, "code-segment")
        elif opcode in (13, 14, 16):
            self.fetch_block = (instruction.sequence,
                                "halt" if opcode == 16 and r1 == 1 else "control")
        return instruction

    def decode(self, instruction, board):
        if instruction.fetch_error or instruction.opcode not in self.vm.opcodes:
            self.fault = instruction.fetch_error or f"illegal opcode {instruction.opcode}"
            self.stop_fetch = True
            self.emit("TRAP", pc=instruction.address, reason=self.fault)
            return False, False
        if instruction.destination is not None and not 0 <= instruction.destination < NUMREGS:
            raise IndexError(f"PC {instruction.address}: indirect destination register is not writable")
        dependencies = {r: board[r] for r in sorted(self.sources(instruction)) if r in board}
        # Compare effective addresses only after pointer/segment registers are
        # available. Address comparison must not itself read or count memory.
        memory_wait = False
        store_address = None
        if not dependencies and self.ex is not None and self.ex.opcode == 8:
            segment = self.vm.reg[DATASEG]
            store_address = self.ex.operand2 + segment
            memory_wait = any(
                self.vm.reg[physical_register(field)] + segment == store_address
                for field in self.operand_fields(instruction) if field & INDIRECT_BIT)
        if dependencies or memory_wait:
            self.stats["data_stalls"] += 1
            instruction.data_stall_cycles += 1
            if not instruction.reported_hazard:
                duration = max([producer["available"] - self.vm.clock
                                for producers in dependencies.values() for producer in producers] +
                               [int(memory_wait)])
                self.emit("RAW", pc=instruction.address, registers=dependencies,
                          memory="older Store to same address before indirect read" if memory_wait else None,
                          memory_address=store_address if memory_wait else None,
                          scoreboard=board, stall_cycles=duration,
                          resume_id_cycle=self.vm.clock + duration)
                instruction.reported_hazard = True
            return False, True
        fields = self.operand_fields(instruction)
        if fields:
            instruction.operand1 = self.vm.getregval(fields[0])
        if instruction.opcode in (1, 2):
            instruction.operand2 = self.vm.getregval(instruction.r2)
        elif self.vm.opcodes[instruction.opcode][0] == 3:
            instruction.operand2 = instruction.immediate
        return True, False

    def execute(self, instruction):
        """Return, EX never reads live operands."""
        vm = self.vm
        vm.ic += 1
        op = instruction.opcode
        a, b = instruction.operand1, instruction.operand2
        result = None
        redirect = None
        flush = False
        overflow = False
        if op == 1:
            result = (a + b) & NUMMASK
            overflow = vm.checkres(a, b, result)
        elif op == 2:
            result = (a - b) & NUMMASK
            overflow = vm.checksubres(a, b, result)
        elif op == 3:
            result = (a - 1) & NUMMASK
        elif op == 4:
            result = (a + 1) & NUMMASK
        elif op == 9:
            result = b
        elif op == 12:
            actual = a != 0
            target = b if actual else instruction.pc + 1
            wrong = instruction.prediction != actual
            self.stats["branches"] += 1
            self.stats["mispredictions"] += int(wrong)
            self.predictor[instruction.address] = actual
            flush = target != instruction.predicted_pc
            if flush:
                redirect = target
                self.stats["control_stalls"] += 2
            self.emit("BRANCH", pc=instruction.address,
                      prediction="T" if instruction.prediction else "N",
                      actual="T" if actual else "N", misprediction=wrong,
                      predicted_pc=instruction.predicted_pc, actual_pc=target,
                      stall_cycles=2 if flush else 0,
                      flush_cycles=2 if flush else 0,
                      predictor={pc: int(bit) for pc, bit in sorted(self.predictor.items())})
        elif op in (13, 14, 16):
            if op == 16 and instruction.r1 == 1:
                self.stop_fetch = True
                self.emit("HALT", pc=instruction.address, action="drain through WB")
            elif op == 16 and instruction.r1 == 0:
                self.fault = "illegal-instruction trap"
                self.stop_fetch = True
                flush = True
                self.emit("TRAP", pc=instruction.address, reason=self.fault)
            else:
                redirect = a if op == 14 else b
                if op in (13, 16):
                    result = instruction.pc + 1
        instruction.result = result
        if overflow:
            instruction.result = None
            self.fault = "arithmetic overflow"
            self.stop_fetch = True
            flush = True
            self.emit("TRAP", pc=instruction.address, reason=self.fault)
        return redirect, flush

    def clear_squashed_block(self, instructions):
        sequences = {entry.sequence for entry in instructions if entry is not None}
        if self.fetch_block and self.fetch_block[0] in sequences:
            self.fetch_block = None

    def run(self, max_cycles):
        vm = self.vm
        if self.trace:
            print("Pipeline: IF ID EX MEM WB; no forwarding; WB writes before ID reads; "
                  "conditional predictor initially N; controls resolve at end of EX")
        while not self.stop_fetch or any((self.id, self.ex, self.mem, self.wb)):
            if vm.clock >= max_cycles:
                raise RuntimeError(f"Pipeline exceeded {max_cycles} cycles; check for an infinite loop")
            vm.clock += 1
            old_id, old_ex, old_mem, old_wb = self.id, self.ex, self.mem, self.wb
            if old_wb is not None:
                if old_wb.result is not None and old_wb.destination is not None:
                    vm.reg[old_wb.destination] = old_wb.result & NUMMASK
                if self.fetch_block == (old_wb.sequence, "code-segment"):
                    self.fetch_block = None

            replay = None
            if old_mem is not None:
                if old_mem.opcode == 7:
                    old_mem.result = vm.getdatamem(old_mem.operand2)
                elif old_mem.opcode == 8:
                    address = old_mem.operand2 + vm.reg[DATASEG]
                    vm.setdatamem(old_mem.operand2, old_mem.operand1)
                    # Unified RAM permits Store to modify code. Replay stale
                    # younger instructions before any of their effects execute.
                    if old_ex is not None and old_ex.address == address:
                        replay = (old_ex, 3)
                    elif old_id is not None and old_id.address == address:
                        replay = (old_id, 2)

            board = self.scoreboard()
            redirect, flush = (None, False)
            replay_applied = False
            replay_ex = replay is not None and replay[0] is old_ex
            if old_ex is not None and not replay_ex:
                redirect, flush = self.execute(old_ex)
            if replay is not None and not flush and redirect is None and not self.stop_fetch:
                redirect = replay[0].pc
                flush = True
                replay_applied = True
                self.stats["replay_stalls"] += replay[1]
                self.emit("CODE_REPLAY", pc=old_mem.address, modified=replay[0].address,
                          replay_pc=redirect, stall_cycles=replay[1])

            advanced, stalled = (False, False)
            if old_id is not None and not flush:
                advanced, stalled = self.decode(old_id, board)

            fetched = None
            block = self.fetch_block
            if not self.stop_fetch and not stalled:
                if block is None:
                    fetched = self.fetch()
                elif block[1] == "control" and not flush:
                    self.stats["control_stalls"] += 1
                    owner = next(entry for entry in (old_id, old_ex)
                                 if entry is not None and entry.sequence == block[0])
                    owner.control_stall_cycles += 1
                elif block[1] == "code-segment" and not flush:
                    self.stats["serialization_stalls"] += 1

            # Report after counting this EX cycle's fetch hold, so the event
            # includes the complete control penalty and keeps RAW waits separate.
            if (old_ex is not None and old_ex.opcode in (13, 14, 16)
                    and redirect is not None and not replay_applied and not replay_ex):
                self.emit("CONTROL", pc=old_ex.address, target=redirect,
                          reason="fetch held until end of EX",
                          stall_cycles=old_ex.control_stall_cycles,
                          data_stall_cycles=old_ex.data_stall_cycles,
                          code_segment_wait=old_ex.destination == CODESEG,
                          scoreboard=board)

            fetched_for_trace = fetched
            if flush:
                discarded = [old_id, fetched] + ([old_ex] if replay_ex else [])
                self.stats["squashed"] += sum(entry is not None for entry in discarded)
                self.clear_squashed_block(discarded)
                self.emit("FLUSH", pc=old_mem.address if replay_applied else old_ex.address,
                          squashed=[self.label(entry) for entry in discarded if entry is not None])
                advanced = stalled = False
                fetched = None
            if redirect is not None:
                self.next_pc = redirect
                if old_ex is not None and self.fetch_block == (old_ex.sequence, "control"):
                    self.fetch_block = None

            row = dict(cycle=vm.clock, IF=self.label(fetched_for_trace), ID=self.label(old_id),
                       EX=self.label(old_ex), MEM=self.label(old_mem), WB=self.label(old_wb),
                       id_stalled=stalled, flushed=flush, scoreboard=board)
            self.timeline.append(row)
            if self.trace:
                print(f"cycle={vm.clock} " + " ".join(f"{stage}={row[stage]}" for stage in
                      ("IF", "ID", "EX", "MEM", "WB")) +
                      f" ID_stalled={stalled} flushed={flush} scoreboard={board}")
            self.wb = old_mem
            self.mem = None if replay_ex else old_ex
            self.ex = old_id if advanced else None
            self.id = old_id if stalled else fetched

        print("Pipeline totals:", " ".join(f"{key}={value}" for key, value in self.stats.items()),
              "predictor=", {pc: int(bit) for pc, bit in sorted(self.predictor.items())})
        return dict(self.stats, predictor=dict(self.predictor), fault=self.fault,
                    events=self.events, timeline=self.timeline)
