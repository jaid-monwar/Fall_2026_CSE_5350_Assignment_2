; Call/return check. BRL writes r5; RET reads that return address.
; Expected r1=1, r5=2. Pipeline IC=5, clock=13, control_stalls=4.
       go 0
0      ldi 1 0
       brl 5 .function
       sys 1 16
.function inc 1
       ret 5
       end
