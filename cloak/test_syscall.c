/*
 * test_syscall.c — Direct syscall origin validation test
 * Tests if Windows 11 Build 26200 blocks syscalls from non-ntdll memory.
 */

#include <windows.h>
#include <stdio.h>

typedef long (NTAPI *pfnNtQSI)(ULONG, PVOID, ULONG, PULONG);

int main(void) {
    printf("\n  Syscall Origin Test\n\n");

    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    BYTE *target = (BYTE *)GetProcAddress(ntdll, "NtQuerySystemInformation");
    printf("  NtQSI at %p\n", target);

    /* Test A: call original NtQSI (class 2, small buffer) */
    {
        pfnNtQSI fn = (pfnNtQSI)target;
        BYTE buf[512]; ULONG ret = 0;
        long st = fn(2, buf, sizeof(buf), &ret);
        printf("  [A] Direct call:          0x%08lX (ret=%lu)\n", st, ret);
    }

    /* Test B: allocate executable page, copy ENTIRE stub, call from there */
    {
        BYTE *page = (BYTE *)VirtualAlloc(NULL, 64,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        memcpy(page, target, 24);  /* copy the entire stub including syscall+ret */
        FlushInstructionCache(GetCurrentProcess(), page, 24);

        pfnNtQSI fn = (pfnNtQSI)page;
        BYTE buf[512]; ULONG ret = 0;
        long st = fn(2, buf, sizeof(buf), &ret);
        printf("  [B] Full stub copy:       0x%08lX (ret=%lu)\n", st, ret);
        VirtualFree(page, 0, MEM_RELEASE);
    }

    /* Test C: copy stub but JMP back to ntdll for syscall */
    {
        BYTE *page = (BYTE *)VirtualAlloc(NULL, 64,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        /* copy first 8 bytes (mov r10, rcx + mov eax, num) */
        memcpy(page, target, 8);
        /* JMP to target+8 (test instruction in ntdll) */
        page[8] = 0x48; page[9] = 0xB8;
        *(UINT64 *)(page + 10) = (UINT64)(target + 8);
        page[18] = 0xFF; page[19] = 0xE0;
        FlushInstructionCache(GetCurrentProcess(), page, 20);

        pfnNtQSI fn = (pfnNtQSI)page;
        BYTE buf[512]; ULONG ret = 0;
        long st = fn(2, buf, sizeof(buf), &ret);
        printf("  [C] 8B copy+JMP ntdll+8:  0x%08lX (ret=%lu)\n", st, ret);
        VirtualFree(page, 0, MEM_RELEASE);
    }

    /* Test D: copy stub, JMP to ntdll syscall directly (skip test+jne) */
    {
        BYTE *page = (BYTE *)VirtualAlloc(NULL, 64,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        /* mov r10, rcx; mov eax, num; JMP to syscall instruction */
        memcpy(page, target, 8);
        page[8] = 0x48; page[9] = 0xB8;
        *(UINT64 *)(page + 10) = (UINT64)(target + 18);  /* syscall instruction */
        page[18] = 0xFF; page[19] = 0xE0;
        FlushInstructionCache(GetCurrentProcess(), page, 20);

        pfnNtQSI fn = (pfnNtQSI)page;
        BYTE buf[512]; ULONG ret = 0;
        long st = fn(2, buf, sizeof(buf), &ret);
        printf("  [D] 8B copy+JMP syscall:  0x%08lX (ret=%lu)\n", st, ret);
        VirtualFree(page, 0, MEM_RELEASE);
    }

    /* Test E: NO copy — JMP directly to NtQSI+0 from alloc'd page */
    {
        BYTE *page = (BYTE *)VirtualAlloc(NULL, 64,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        page[0] = 0x48; page[1] = 0xB8;
        *(UINT64 *)(page + 2) = (UINT64)target;
        page[10] = 0xFF; page[11] = 0xE0;
        FlushInstructionCache(GetCurrentProcess(), page, 12);

        pfnNtQSI fn = (pfnNtQSI)page;
        BYTE buf[512]; ULONG ret = 0;
        long st = fn(2, buf, sizeof(buf), &ret);
        printf("  [E] Pure JMP to NtQSI+0:  0x%08lX (ret=%lu)\n", st, ret);
        VirtualFree(page, 0, MEM_RELEASE);
    }

    printf("\n  Expected for class 2: 0xC0000004 (buffer too small)\n");
    printf("  0xC000001C = STATUS_INVALID_SYSTEM_SERVICE (blocked)\n\n");

    return 0;
}
