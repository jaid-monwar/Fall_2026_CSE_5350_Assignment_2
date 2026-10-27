; One-bit predictor check: outcomes T,T,N; predictions N,T,T.
; Expected r1=0; predictor entry at PC 2 ends at N; two mispredictions.
; Pipeline: IC=8, clock=24, data_stalls=8, control_stalls=4.
; Wrong-path instructions are fetched but never execute or change registers.
       go 0
0      ldi 1 3
.loop  dec 1
       bnz 1 .loop
       sys 1 16
       end
