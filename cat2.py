#!/usr/bin/env python3


# (c) DL, UTA, 2009 - 2026

# ---------- CAT2 architecture parameters ----------
# Change fundamental machine parameters here only.  Derived masks/positions are
# calculated below and are shared by assembler.py and execute.py.
WORDSIZE = 31
NUMREGBITS = 3                         # register number bits; one extra field bit is the indirect flag
OPCODESIZE = 7
MEMLOADSIZE = 1024

# ---------- Derived architecture values ----------
NUMREGS = 1 << NUMREGBITS
INDIRECT_BIT = 1 << NUMREGBITS
REG_FIELD_BITS = NUMREGBITS + 1
REGMASK = (1 << REG_FIELD_BITS) - 1
OPCPOSITION = WORDSIZE - (OPCODESIZE + 1)
REG1POSITION = OPCPOSITION - REG_FIELD_BITS
REG2POSITION = REG1POSITION - REG_FIELD_BITS
MEMADDRIMMEDPOSITION = REG2POSITION
ADDRSIZE = MEMADDRIMMEDPOSITION
ADDMASK = (1 << ADDRSIZE) - 1
NUMMASK = (1 << WORDSIZE) - 1
OPCODEMASK = (1 << OPCODESIZE) - 1
REALMEMSIZE = MEMLOADSIZE

# memory management regs
CODESEG = NUMREGS - 1                  # last reg is a code segment pointer
DATASEG = NUMREGS - 2                  # next to last reg is a data segment pointer

# ints and traps
TRAPREGLINK = NUMREGS - 3              # store return value here
TRAPVAL = NUMREGS - 4                  # pass which trap/int

# ---------- Assignment-wide architectural assumptions ----------
# The handout uses a 5-stage IF/ID/EX/MEM/WB model.  For Part 2, use the
# instructor-selected simple model with NO forwarding.  Students must determine
# hazards and exact stalls from that model.
PIPELINE_STAGES = ("IF", "ID", "EX", "MEM", "WB")
FORWARDING = False

# Part 3 timing constants come directly from the assignment handout.
L1_LATENCY = 1
L2_LATENCY = 4
MEM_LATENCY = 25


# Students must implement the cache behavior/timing in Part 3.
WRITE_POLICY = "write-through"
WRITE_ALLOCATE = True
IDEAL_WRITE_BUFFER = True

# ---------- Base CAT2 ISA ----------
# type values preserve the professor's original skeleton convention:
#   1=one-reg, 2=two-reg, 3=reg+addr/immed, 4=data/pseudo (dw), 0=end
#
# NOTE: 'st' uses the opcode assigned by the original skeleton.
# PART 1 TODO (ADDRESSED): its execution and baseline measurements are in execute.py.
# Part 4 vector instructions are intentionally absent; students must add them.
INSTRUCTION_SET = {
    "add": {"type": 2, "opcode": 1},
    "sub": {"type": 2, "opcode": 2},
    "dec": {"type": 1, "opcode": 3},
    "inc": {"type": 1, "opcode": 4},
    "ld":  {"type": 3, "opcode": 7},
    "st":  {"type": 3, "opcode": 8},
    "ldi": {"type": 3, "opcode": 9},
    "bnz": {"type": 3, "opcode": 12},
    "brl": {"type": 3, "opcode": 13},
    "ret": {"type": 1, "opcode": 14},
    "int": {"type": 3, "opcode": 16},
    "dw":  {"type": 4, "opcode": 0, "pseudo": True},
    "go":  {"type": 3, "opcode": 0, "pseudo": True},
    "end": {"type": 0, "opcode": 0, "pseudo": True},
}

ALIASES = {"sys": "int"}


def canonical_mnemonic(mnemonic):
    """Return the canonical mnemonic for an assembler alias."""
    name = mnemonic.lower()
    return ALIASES.get(name, name)


def instruction_info(mnemonic):
    """Return shared ISA metadata for a mnemonic or alias."""
    return INSTRUCTION_SET[canonical_mnemonic(mnemonic)]


# Assembler compatibility table: mnemonic -> (type, opcode), including aliases.
ASSEMBLER_OPCODES = {
    name: (info["type"], info["opcode"])
    for name, info in INSTRUCTION_SET.items()
}
for alias, canonical in ALIASES.items():
    info = INSTRUCTION_SET[canonical]
    ASSEMBLER_OPCODES[alias] = (info["type"], info["opcode"])

# Executor compatibility table: opcode -> (type, canonical mnemonic).
EXECUTOR_OPCODES = {
    info["opcode"]: (info["type"], name)
    for name, info in INSTRUCTION_SET.items()
    if not info.get("pseudo")
}


def physical_register(encoded_register):
    """Strip the indirect bit and return the physical base register number."""
    return encoded_register & (NUMREGS - 1)


def validate_architecture():
    """Fail early if the configured CAT2 bit fields cannot form a valid word."""
    if WORDSIZE <= 0 or NUMREGBITS <= 0 or OPCODESIZE <= 0:
        raise ValueError("CAT2 word/register/opcode sizes must be positive")
    if REG2POSITION <= 0:
        raise ValueError(
            "CAT2 word is too small for opcode + two register fields + address/immediate"
        )
    largest_opcode = max(info["opcode"] for info in INSTRUCTION_SET.values())
    if largest_opcode > OPCODEMASK:
        raise ValueError("OPCODESIZE is too small for the configured instruction set")
    if MEMLOADSIZE <= 0:
        raise ValueError("MEMLOADSIZE must be positive")
    if MEMLOADSIZE - 1 > ADDMASK:
        raise ValueError(
            "MEMLOADSIZE exceeds the address/immediate field; increase WORDSIZE or reduce memory"
        )


validate_architecture()

# Lower-case aliases keep the original CAT2 variable names readable in the
# modernized starter while all values originate from this one file.
wordsize = WORDSIZE
numregbits = NUMREGBITS
opcodesize = OPCODESIZE
memloadsize = MEMLOADSIZE
numregs = NUMREGS
regmask = REGMASK
opcposition = OPCPOSITION
reg1position = REG1POSITION
reg2position = REG2POSITION
memaddrimmedposition = MEMADDRIMMEDPOSITION
addmask = ADDMASK
nummask = NUMMASK
realmemsize = REALMEMSIZE
codeseg = CODESEG
dataseg = DATASEG
trapreglink = TRAPREGLINK
trapval = TRAPVAL
opcodes_assembler = ASSEMBLER_OPCODES
opcodes_executor = EXECUTOR_OPCODES
