#!/usr/bin/env python3
# (c) DL, UTA, 2009 - 2026


import argparse

from cat2 import (
    ADDMASK,
    ASSEMBLER_OPCODES,
    NUMREGS,
    memaddrimmedposition,
    memloadsize,
    numregbits,
    opcposition,
    opcodesize,
    reg1position,
    reg2position,
    wordsize,
)

SOURCE_FILE = "in.asm"
startexecptr = 0
mem = [0] * memloadsize                              # this is the memory load executable

# instruction mnemonic, type: (1 reg, 2 reg, reg+addr, immed, pseudoop), opcode
opcodes = dict(ASSEMBLER_OPCODES)


def parse_int(s):
    """Parse decimal or Python-style 0x/0o/0b integer text."""
    return int(s, 0)


def strip_comment(line):
    """Remove a full-line or trailing ';' comment."""
    if ';' in line:
        return line.split(';', 1)[0]
    return line


def tokenize(line):
    """Tokenize one assembly source line."""
    line = strip_comment(line).strip()
    if not line:
        return []
    return line.split()


def is_address_token(tok):
    """True when tok is a decimal/hex/octal/binary integer."""
    try:
        parse_int(tok)
        return True
    except ValueError:
        return False


def regval(rstr):
    """Encode register or indirect: '3' -> 3, '*3' -> indirect register 3."""
    indirect = rstr.startswith('*')
    number_text = rstr[1:] if indirect else rstr
    try:
        reg_number = parse_int(number_text)
    except ValueError as exc:
        raise ValueError(f"Invalid register '{rstr}'") from exc

    if not 0 <= reg_number < NUMREGS:
        raise ValueError(f"Register '{rstr}' is out of range 0..{NUMREGS - 1}")

    if indirect:
        return reg_number + (1 << numregbits)
    return reg_number


def require_address_range(value, description):
    """Check that an encoded address/immediate fits the CAT2 low field."""
    if value < 0 or value > ADDMASK:
        raise ValueError(
            f"{description} {value} does not fit in the {memaddrimmedposition}-bit "
            f"CAT2 address/immediate field (0..{ADDMASK})"
        )
    return value


def assemble(source_file, output_file="a.out"):
    """Assemble one CAT2 source file and return its symbol table."""
    global startexecptr, mem

    startexecptr = 0
    mem = [0] * memloadsize

    # Build Symbol Table -- first pass
    symboltable = {}
    curaddr = 0

    with open(source_file, "r", encoding="utf-8") as infile:
        for line_number, raw in enumerate(infile, 1):
            tokens = tokenize(raw)                    # tokens on each line
            if not tokens:
                continue

            if is_address_token(tokens[0]):           # if line starts with an address
                curaddr = parse_int(tokens[0])        # assemble to here
                if curaddr < 0 or curaddr >= memloadsize:
                    raise ValueError(
                        f"Line {line_number}: origin {curaddr} is outside memory 0..{memloadsize - 1}"
                    )
                tokens = tokens[1:]
                if not tokens:
                    continue

            firsttoken = tokens[0].lower()

            if firsttoken == 'go':                    # start execution here
                if len(tokens) != 2:
                    raise ValueError(f"Line {line_number}: go requires exactly 1 address")
                start = parse_int(tokens[1])
                require_address_range(start, "go address")
                startexecptr = start
                continue

            if tokens[0].startswith('.'):
                label = tokens[0]
                if label in symboltable:
                    raise ValueError(f"Line {line_number}: duplicate label {label}")
                symboltable[label] = curaddr
                tokens = tokens[1:]
                if not tokens:
                    continue
                firsttoken = tokens[0].lower()

            if firsttoken == 'end':
                break
            if firsttoken not in opcodes:
                raise ValueError(f"Line {line_number}: unknown opcode '{firsttoken}'")

            if curaddr >= memloadsize:
                raise IndexError(
                    f"Line {line_number}: address {curaddr} is outside load image 0..{memloadsize - 1}"
                )
            curaddr += 1

    # Second pass -- encode instructions and data
    curaddr = 0
    with open(source_file, "r", encoding="utf-8") as infile:
        for line_number, raw in enumerate(infile, 1):
            tokens = tokenize(raw)
            if not tokens:
                continue

            if is_address_token(tokens[0]):
                curaddr = parse_int(tokens[0])
                if curaddr < 0 or curaddr >= memloadsize:
                    raise ValueError(
                        f"Line {line_number}: origin {curaddr} is outside memory 0..{memloadsize - 1}"
                    )
                tokens = tokens[1:]
                if not tokens:
                    continue

            if tokens[0].lower() == 'go':
                if len(tokens) != 2:
                    raise ValueError(f"Line {line_number}: go requires exactly 1 address")
                start = parse_int(tokens[1])
                require_address_range(start, "go address")
                startexecptr = start
                continue

            if tokens[0].startswith('.'):
                tokens = tokens[1:]
                if not tokens:
                    continue

            mnem = tokens[0].lower()
            if mnem == 'end':
                break

            memdata = 0                               # build instruction step by step

            if mnem == 'dw':                          # dw type
                if len(tokens) != 2:
                    raise ValueError(f"Line {line_number}: dw requires exactly 1 value")
                memdata = parse_int(tokens[1]) & ((1 << wordsize) - 1)
            else:
                if mnem not in opcodes:
                    raise ValueError(f"Line {line_number}: unknown opcode '{mnem}'")

                instype, opcode = opcodes[mnem]
                memdata = (opcode & ((1 << opcodesize) - 1)) << opcposition

                if instype == 1:                      # dec,inc type, one reg
                    if len(tokens) != 2:
                        raise ValueError(f"Line {line_number}: {mnem} requires 1 operand")
                    r1 = regval(tokens[1])
                    # A write destination must be a real register, not an indirect field.
                    if mnem in ('dec', 'inc') and r1 >= NUMREGS:
                        raise ValueError(f"Line {line_number}: {mnem} destination must be direct")
                    memdata |= r1 << reg1position

                elif instype == 2:                    # add, sub type, two regs
                    if len(tokens) != 3:
                        raise ValueError(f"Line {line_number}: {mnem} requires 2 operands")
                    r1 = regval(tokens[1])
                    r2 = regval(tokens[2])
                    if mnem in ('add', 'sub') and r1 >= NUMREGS:
                        raise ValueError(f"Line {line_number}: {mnem} destination must be direct")
                    memdata |= (r1 << reg1position) | (r2 << reg2position)

                elif instype == 3:                    # ld,st,ldi,bnz,brl,int type
                    if len(tokens) != 3:
                        raise ValueError(
                            f"Line {line_number}: {mnem} requires 2 operands (reg, addr/label)"
                        )
                    r1 = regval(tokens[1])
                    if mnem in ('ld', 'ldi', 'brl') and r1 >= NUMREGS:
                        raise ValueError(f"Line {line_number}: {mnem} destination must be direct")
                    t2 = tokens[2]
                    if is_address_token(t2):
                        memaddr = parse_int(t2)
                    else:
                        if t2 not in symboltable:
                            raise ValueError(f"Line {line_number}: unknown label {t2}")
                        memaddr = symboltable[t2]
                    require_address_range(memaddr, f"Line {line_number} address/immediate")
                    memdata |= (r1 << reg1position) | (memaddr & ADDMASK)

            if curaddr < 0 or curaddr >= memloadsize:
                raise IndexError(f"Address {curaddr} out of load image bounds (0..{memloadsize-1})")
            mem[curaddr] = memdata                     # memory image at the current location
            curaddr += 1

    with open(output_file, "w", encoding="utf-8") as outfile:
        outfile.write(f"go {startexecptr}\n")         # start execution here
        for i in range(memloadsize):                   # write memory image
            outfile.write(f"{hex(mem[i])}    {i}\n")

    return symboltable


def main():
    parser = argparse.ArgumentParser(description="Assemble CAT2 assembly into a.out")
    parser.add_argument("source", nargs="?", default=SOURCE_FILE,
                        help="CAT2 assembly source file (default: in.asm)")
    parser.add_argument("-o", "--output", default="a.out",
                        help="output load image (default: a.out)")
    args = parser.parse_args()
    assemble(args.source, args.output)
    print(f"Assembled {args.source} -> {args.output}")


if __name__ == "__main__":
    main()
