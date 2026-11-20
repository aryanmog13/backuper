#include <errno.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char executable[PATH_MAX];
    char resolved[PATH_MAX];
    uint32_t capacity = sizeof(executable);

    if (_NSGetExecutablePath(executable, &capacity) != 0 || realpath(executable, resolved) == NULL) {
        fputs("Backuper could not locate its macOS launcher.\n", stderr);
        return EXIT_FAILURE;
    }

    char *filename = strrchr(resolved, '/');
    *filename = '\0';
    char script[PATH_MAX];
    int size = snprintf(script, sizeof(script), "%s/../Resources/launch-backuper.sh", resolved);
    if (size < 0 || size >= (int)sizeof(script)) {
        fputs("The Backuper installation path is too long.\n", stderr);
        return EXIT_FAILURE;
    }

    char **arguments = calloc((size_t)argc + 2, sizeof(*arguments));
    if (arguments == NULL) {
        return EXIT_FAILURE;
    }
    arguments[0] = "/bin/sh";
    arguments[1] = script;
    for (int i = 1; i < argc; ++i) {
        arguments[i + 1] = argv[i];
    }

    execv(arguments[0], arguments);
    fprintf(stderr, "Backuper could not start: %s\n", strerror(errno));
    free(arguments);
    return EXIT_FAILURE;
}
