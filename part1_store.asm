; Part 1 Store/load check.
; Expected: memory[4] = 42, r1 = 42, r2 = 42.
; Executed instructions = 4 (including sys halt).
; Clock cycles = 20, instruction refs = 4, data refs = 2, total refs = 6.

       go 0
0      ldi 1 42
       st  1 .target
       ld  2 .target
       sys 1 16
.target dw 0
       end
