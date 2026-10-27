#!/usr/bin/env python3
# (c) DL, UTA, 2009 - 2026

import argparse
import sys
import time

from cat2 import (
    ADDMASK,
    EXECUTOR_OPCODES,
    NUMMASK,
    NUMREGS,
    dataseg,
    memloadsize,
    nummask,
    numregbits,
    numregs,
    opcposition,
    physical_register,
    realmemsize,
    reg1position,
    reg2position,
    regmask,
    codeseg,
    trapreglink,
    trapval,
    wordsize,
)

addmask = ADDMASK

mem = [0] * realmemsize                              # this is memory, init to 0
reg = [0] * numregs                                  # registers
clock = 0                                            # PART 1 TODO (ADDRESSED): elapsed VM cycles
ic = 0                                               # PART 1 TODO (ADDRESSED): decoded/executed instructions
numcoderefs = 0                                      # PART 1 TODO (ADDRESSED): instruction fetches
numdatarefs = 0                                      # PART 1 TODO (ADDRESSED): data reads and writes
starttime = time.time()

opcodes = dict(EXECUTOR_OPCODES)


def reset_state():
    """Reset the  VM for a clean execution."""
    global mem, reg, clock, ic, numcoderefs, numdatarefs, starttime
    mem = [0] * realmemsize
    reg = [0] * numregs
    clock = 0
    ic = 0
    numcoderefs = 0
    numdatarefs = 0
    starttime = time.time()


def startexechere(p):
    # start execution at this address
    if p < 0 or p >= realmemsize:
        raise ValueError(f"Start execution address {p} outside memory")
    reg[codeseg] = p


def check_memory_address(addr):
    """Reject negative or out-of-range CAT2 addresses."""
    if addr < 0 or addr >= realmemsize:
        raise IndexError(f"CAT2 memory address {addr} outside 0..{realmemsize - 1}")


def loadmem(filename="a.out"):
    # get binary load image
    curaddr = 0
    with open(filename, "r", encoding="utf-8") as infile:
        for line_number, line in enumerate(infile, 1):
            tokens = line.lower().split()             # first token on each line is mem word
            if not tokens:
                continue
            if tokens[0] == 'go':
                if len(tokens) < 2:
                    raise ValueError(f"{filename}:{line_number}: malformed go header")
                startexechere(int(tokens[1], 0))
            else:
                if curaddr >= realmemsize:
                    raise IndexError(f"{filename} contains more than {realmemsize} memory words")
                mem[curaddr] = int(tokens[0], 0) & nummask
                curaddr += 1


def getcodemem(a):
    # get code memory at this address
    global numcoderefs
    addr = a + reg[codeseg]
    check_memory_address(addr)

    # PART 1 TODO (ADDRESSED): count an instruction-memory reference here.
    numcoderefs += 1
    # PART 3 TODO: route this reference through the instruction/unified L1 cache.

    return mem[addr]


def getdatamem(a):
    # get data memory at this address
    global numdatarefs
    addr = a + reg[dataseg]
    check_memory_address(addr)

    # PART 1 TODO (ADDRESSED): count a data-memory reference here.
    numdatarefs += 1
    # PART 3 TODO: route this reference through the data/unified L1 cache.

    return mem[addr]


def setdatamem(a, v):
    """Write one masked data word and count the Store reference."""
    # PART 1 TODO (ADDRESSED): implement the ST memory write and data reference.
    global numdatarefs
    addr = a + reg[dataseg]
    check_memory_address(addr)

    numdatarefs += 1
    mem[addr] = v & nummask
    # PART 3 TODO: once the cache is implemented, apply the required write policy.


def getregval(r):
    # get reg or indirect value
    base = physical_register(r)
    if (r & (1 << numregbits)) == 0:                 # not indirect
        return reg[base]
    return getdatamem(reg[base])                     # indirect data with mem address


def checkres(v1, v2, res):
    """Signed addition overflow detector at the configured CAT2 word width."""
    v1sign = (v1 >> (wordsize - 1)) & 1
    v2sign = (v2 >> (wordsize - 1)) & 1
    ressign = (res >> (wordsize - 1)) & 1
    if v1sign and v2sign and not ressign:
        return 1
    if (not v1sign) and (not v2sign) and ressign:
        return 1
    return 0


def checksubres(v1, v2, res):
    """Signed subtraction overflow detector at the configured CAT2 word width."""
    v1sign = (v1 >> (wordsize - 1)) & 1
    v2sign = (v2 >> (wordsize - 1)) & 1
    ressign = (res >> (wordsize - 1)) & 1
    return int((v1sign != v2sign) and (ressign != v1sign))


def dumpstate(d):
    # dump contents / metadata of registers and memory
    if d == 1:
        print(reg)
    elif d == 2:
        print(mem)
    elif d == 3:
        print(
            'clock=', clock,
            'IC=', ic,
            'Coderefs=', numcoderefs,
            'Datarefs=', numdatarefs,
            'Totalrefs=', numcoderefs + numdatarefs,
            'Start Time=', starttime,
            'Currently=', time.time(),
        )


def trap(t):
    # unusual cases
    # trap 0 illegal instruction
    # trap 1 arithmetic overflow
    # trap 2 sys call
    # trap 3+ user
    rl = trapreglink                              # store return value here
    rv = trapval
    if t in (0, 1):
        dumpstate(1)
        dumpstate(2)
        dumpstate(3)
        return -1, -1
    return rv, rl


# ---------------------------------------------------------------------------
# PART 2 TODO (ADDRESSED): Pipeline hazards and branch prediction
# ---------------------------------------------------------------------------
# Use the 5-stage IF/ID/EX/MEM/WB pipeline and NO-forwarding assumption stated
# in cat2.py.  Students must implement:
#   * a scoreboard (or similar) for RAW data hazards,
#   * exact stall-duration calculation,
#   * reporting of where/why each hazard occurs and scoreboard contents,
#   * control-hazard handling/stalls, and
#   * a one-bit branch predictor with visible predictor-table contents.


# ---------------------------------------------------------------------------
# PART 3 TODO: L1 cache
# ---------------------------------------------------------------------------
# Implement the cache configurations specified in the assignment handout.
# Cache access logic, tag/index calculation, hit/miss handling, replacement,
# data storage, timing, statistics, and cache dumps.

# ---------------------------------------------------------------------------
# PART 4 TODO: Vector instructions
# ---------------------------------------------------------------------------
# Add the required vector-add and vector-sum instructions to cat2.py, extend the
# assembler/decoder as needed, implement their execution semantics, and modify
# the 5-stage timing/model as required by the assignment.


def finish_run(dump_memory, pipeline_result=None):
    """Report final architectural state for either execution model."""
    dumpstate(1)
    if dump_memory:
        dumpstate(2)
    dumpstate(3)
    result = {
        "registers": list(reg),
        "clock": clock,
        "ic": ic,
        "code_refs": numcoderefs,
        "data_refs": numdatarefs,
        "total_refs": numcoderefs + numdatarefs,
    }
    if pipeline_result is not None:
        result["pipeline"] = pipeline_result
    return result


def run_vm(executable_file="a.out", dump_memory=False, pipeline=False,
           trace=True, max_cycles=100000):
    global clock, ic

    reset_state()
    startexechere(0)                                  # start execution here if no "go"
    loadmem(executable_file)                          # load binary executable
    if pipeline:
        from pipeline import Pipeline
        model = Pipeline(sys.modules[__name__], trace=trace)
        pipeline_result = model.run(max_cycles=max_cycles)
        return finish_run(dump_memory, pipeline_result)
    ip = 0                                            # start execution at codeseg location 0

    # while instruction is not halt
    while True:
        ir = getcodemem(ip)                           # - fetch
        ip = ip + 1
        opcode = ir >> opcposition                    # - decode
        reg1 = (ir >> reg1position) & regmask
        reg2 = (ir >> reg2position) & regmask
        addr = ir & addmask

        # PART 2 TODO (ADDRESSED): perform scoreboard/data-hazard and control-hazard work
        #               at the appropriate points in the instruction flow.

        # - operand fetch
        if opcode not in opcodes:
            tval, treg = trap(0)
            if tval == -1:                           # illegal instruction
                break

        instype = opcodes[opcode][0]
        # PART 1 TODO (ADDRESSED): count the dynamic instruction and its
        # five-cycle, non-overlapped baseline execution.
        # A valid decoded instruction counts even if it later traps. An illegal
        # fetched opcode counts as a code reference but not an executed instruction.
        ic += 1
        clock += 5  # Part 1 non-overlapped IF/ID/EX/MEM/WB baseline.
        operand1 = 0
        operand2 = 0
        memdata = 0                                   # contents of memory for loads

        if instype == 1:                              # dec, inc, ret type
            operand1 = getregval(reg1)                # fetch operands
        elif instype == 2:                            # add, sub type
            operand1 = getregval(reg1)
            operand2 = getregval(reg2)
        elif instype == 3:                            # ld, st, br type
            # LD and LDI do not need the old destination-register value.
            if opcode in (8, 12):                     # ST/BNZ read reg1
                operand1 = getregval(reg1)
            operand2 = addr
        else:
            break

        if opcode == 7:                               # get data memory for loads
            memdata = getdatamem(operand2)

        # execute
        result = None
        halt_requested = False

        if opcode == 1:                               # add
            result = (operand1 + operand2) & NUMMASK
            if checkres(operand1, operand2, result):
                tval, treg = trap(1)
                if tval == -1:                       # overflow
                    break

        elif opcode == 2:                             # sub
            result = (operand1 - operand2) & NUMMASK
            if checksubres(operand1, operand2, result):
                tval, treg = trap(1)
                if tval == -1:
                    break

        elif opcode == 3:                             # dec
            result = (operand1 - 1) & NUMMASK

        elif opcode == 4:                             # inc
            result = (operand1 + 1) & NUMMASK

        elif opcode == 7:                             # load
            result = memdata

        elif opcode == 8:                             # store
            # PART 1 TODO (ADDRESSED): execute ST through setdatamem().
            setdatamem(operand2, operand1)

        elif opcode == 9:                             # load immediate
            result = operand2

        elif opcode == 12:                            # conditional branch
            result = operand1
            if result != 0:
                ip = operand2

        elif opcode == 13:                            # branch and link
            result = ip
            ip = operand2

        elif opcode == 14:                            # return
            ip = operand1

        elif opcode == 16:                            # interrupt/sys call
            # The supplied benchmark uses "sys 1 16" as a halt request.
            if reg1 == 1:
                halt_requested = True
                result = None
            else:
                result = ip
                tval, treg = trap(reg1)
                if tval == -1:
                    break
                reg1 = treg
                ip = operand2

        # write back
        if result is not None:
            if opcode in (1, 2, 3, 4, 7, 9):          # arithmetic + loads
                if reg1 >= NUMREGS:
                    raise IndexError("Indirect destination register is not writable")
                reg[reg1] = result & nummask
            elif opcode in (13, 16):                  # store return address
                if reg1 >= NUMREGS:
                    raise IndexError("Invalid link destination register")
                reg[reg1] = result & nummask

        if halt_requested:
            break

    return finish_run(dump_memory)


def main():
    parser = argparse.ArgumentParser(description="Run the CAT2 virtual machine")
    parser.add_argument("--aout", default="a.out",
                        help="assembler load image to execute (default: a.out)")
    parser.add_argument("--dump-memory", action="store_true",
                        help="print the complete memory image after execution")
    parser.add_argument("--pipeline", action="store_true",
                        help="use the Part 2 five-stage pipeline with hazards and prediction")
    parser.add_argument("--no-trace", action="store_true",
                        help="suppress pipeline cycle and event traces; keep final totals")
    parser.add_argument("--max-cycles", type=int, default=100000,
                        help="stop a pipeline run after this many cycles (default: 100000)")
    args = parser.parse_args()
    run_vm(args.aout, dump_memory=args.dump_memory, pipeline=args.pipeline,
           trace=not args.no_trace, max_cycles=args.max_cycles)


if __name__ == "__main__":
    main()
