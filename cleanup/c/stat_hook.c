/*
 * stat_hook.c — POSIX file-size probe
 *
 * Callable as a CGO source by go/scanner/main.go on non-Windows platforms.
 * Also compiles to a standalone binary (make -C c/ stat-hook) for use from
 * plain shell scripts when Go is not available.
 *
 * Standalone usage: stat-hook <path>
 *   stdout: <size_bytes>\t<path>
 *   exit 0 on success, 1 on error (message to stderr)
 *
 * CGO usage: see go/scanner/posix.go
 */

#ifndef _XOPEN_SOURCE
#define _XOPEN_SOURCE 700
#endif

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

/* ── CGO-visible exports ────────────────────────────────────────────────── */

typedef struct {
    int64_t size;
    int     err;               /* 0 = ok, else errno value */
    char    msg[256];
} stat_result_t;

static stat_result_t stat_hook_size(const char *path) {
    stat_result_t r = {0, 0, {0}};
    struct stat st;
    if (stat(path, &st) != 0) {
        r.err = errno;
        strncpy(r.msg, strerror(errno), sizeof(r.msg) - 1);
    } else {
        r.size = (int64_t)st.st_size;
    }
    return r;
}

/* ── Standalone entry point ─────────────────────────────────────────────── */

#ifndef STAT_HOOK_LIB_ONLY
int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "usage: stat-hook <path>\n");
        return 1;
    }
    stat_result_t r = stat_hook_size(argv[1]);
    if (r.err != 0) {
        fprintf(stderr, "stat-hook: %s: %s\n", argv[1], r.msg);
        return 1;
    }
    printf("%lld\t%s\n", (long long)r.size, argv[1]);
    return 0;
}
#endif
