; No-forwarding checks: four RAW dependencies, each requiring two stalls.
; Expected r1=6, r2=7, r4=13, memory[9]=7.
; Pipeline: IC=8, clock=20, data_stalls=8, control_stalls=0.
; Instruction refs=8, data refs=3 (indirect read, Store, Load), total refs=11.
       go 0
0      ldi 1 5
       inc 1
       ldi 3 .value
       add 2 *3
       st  2 .saved
       ld  4 .saved
       add 4 1
       sys 1 16
.value dw 7
.saved dw 0
       end
