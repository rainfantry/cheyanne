/*
 * hook_engine.c — x64 Inline Hook Engine
 * 22DIV / george wu
 *
 * 12-byte absolute JMP: mov rax, <addr>; jmp rax
 *
 * Two trampoline modes:
 *   self_contained=TRUE:  full NT stub copy (24B incl. syscall+ret).
 *                         No JMP back to ntdll. Required on Win11 26200+
 *                         which blocks mid-function entry into NT stubs.
 *   self_contained=FALSE: saved bytes + JMP back to target+N.
 *                         Used for non-NT functions (iphlpapi etc).
 */

#include "hook_engine.h"

void hook_write_jmp(BYTE *dst, void *target) {
    dst[0] = 0x48;                                  /* REX.W */
    dst[1] = 0xB8;                                  /* mov rax, imm64 */
    *(UINT64 *)(dst + 2) = (UINT64)target;
    dst[10] = 0xFF;                                 /* jmp rax */
    dst[11] = 0xE0;
}

BOOL hook_install(HOOK_ENTRY *h) {
    if (!h || !h->target || !h->hook || h->installed)
        return FALSE;

    if (h->save_size < HOOK_PATCH_SIZE || h->save_size > HOOK_SAVE_MAX)
        return FALSE;

    /*
     * Trampoline layout depends on whether the saved region contains
     * a syscall. For NT stubs (ntdll), the entire 24-byte stub must
     * be self-contained in the trampoline — Windows 11 26200+ rejects
     * mid-function entry into ntdll syscall stubs. For non-syscall
     * functions (iphlpapi etc), the trampoline JMPs back to target.
     */
    DWORD tramp_size;
    if (h->self_contained)
        tramp_size = h->save_size;  /* no JMP back needed */
    else
        tramp_size = h->save_size + HOOK_PATCH_SIZE;

    BYTE *tramp = (BYTE *)VirtualAlloc(
        NULL, tramp_size, MEM_COMMIT | MEM_RESERVE,
        PAGE_EXECUTE_READWRITE
    );
    if (!tramp) return FALSE;

    memcpy(h->saved_bytes, h->target, h->save_size);
    memcpy(tramp, h->saved_bytes, h->save_size);

    if (!h->self_contained)
        hook_write_jmp(tramp + h->save_size, (BYTE *)h->target + h->save_size);

    h->trampoline = tramp;

    DWORD oldProt;
    if (!VirtualProtect(h->target, h->save_size, PAGE_EXECUTE_READWRITE, &oldProt))
        goto fail;

    hook_write_jmp((BYTE *)h->target, h->hook);

    for (DWORD i = HOOK_PATCH_SIZE; i < h->save_size; i++)
        *((BYTE *)h->target + i) = 0x90;

    DWORD dummy;
    VirtualProtect(h->target, h->save_size, oldProt, &dummy);

    FlushInstructionCache(GetCurrentProcess(), h->target, h->save_size);
    FlushInstructionCache(GetCurrentProcess(), tramp, tramp_size);

    h->installed = TRUE;
    return TRUE;

fail:
    VirtualFree(tramp, 0, MEM_RELEASE);
    h->trampoline = NULL;
    return FALSE;
}

BOOL hook_remove(HOOK_ENTRY *h) {
    if (!h || !h->installed)
        return FALSE;

    DWORD oldProt;
    if (!VirtualProtect(h->target, h->save_size, PAGE_EXECUTE_READWRITE, &oldProt))
        return FALSE;

    memcpy(h->target, h->saved_bytes, h->save_size);

    DWORD dummy;
    VirtualProtect(h->target, h->save_size, oldProt, &dummy);
    FlushInstructionCache(GetCurrentProcess(), h->target, h->save_size);

    if (h->trampoline) {
        VirtualFree(h->trampoline, 0, MEM_RELEASE);
        h->trampoline = NULL;
    }

    h->installed = FALSE;
    return TRUE;
}
