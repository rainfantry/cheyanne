/*
 * hook_engine.h — x64 Inline Hook Engine
 * 22DIV / george wu
 *
 * 12-byte absolute JMP patch (mov rax, addr; jmp rax).
 * Saves 16 bytes to align on NT stub instruction boundaries.
 * Trampoline: saved bytes + absolute JMP back.
 */

#ifndef HOOK_ENGINE_H
#define HOOK_ENGINE_H

#include <windows.h>

#define HOOK_PATCH_SIZE  12
#define HOOK_SAVE_MAX    32

typedef struct _HOOK_ENTRY {
    void   *target;
    void   *hook;
    void   *trampoline;
    BYTE    saved_bytes[HOOK_SAVE_MAX];
    DWORD   save_size;     /* bytes to save — must land on instruction boundary */
    BOOL    self_contained; /* TRUE = trampoline has full stub incl. syscall+ret, no JMP back */
    BOOL    installed;
} HOOK_ENTRY;

BOOL hook_install(HOOK_ENTRY *h);
BOOL hook_remove(HOOK_ENTRY *h);
void hook_write_jmp(BYTE *dst, void *target);

#endif
