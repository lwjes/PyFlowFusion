#include <dirent.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

int LLVMFuzzerInitialize(int *argc, char ***argv);
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);

static size_t files_processed = 0;

static int replay_path(const char *path);

static int replay_file(const char *path) {
    FILE *fp = fopen(path, "rb");
    long file_size;
    uint8_t *buffer;

    if (fp == NULL) {
        fprintf(stderr, "[replay] failed to open %s: %s\n", path, strerror(errno));
        return 1;
    }

    if (fseek(fp, 0, SEEK_END) != 0) {
        fprintf(stderr, "[replay] failed to seek %s: %s\n", path, strerror(errno));
        fclose(fp);
        return 1;
    }
    file_size = ftell(fp);
    if (file_size < 0) {
        fprintf(stderr, "[replay] failed to tell %s: %s\n", path, strerror(errno));
        fclose(fp);
        return 1;
    }
    if (fseek(fp, 0, SEEK_SET) != 0) {
        fprintf(stderr, "[replay] failed to rewind %s: %s\n", path, strerror(errno));
        fclose(fp);
        return 1;
    }

    buffer = (uint8_t *)malloc((size_t)file_size);
    if (buffer == NULL && file_size > 0) {
        fprintf(stderr, "[replay] out of memory reading %s\n", path);
        fclose(fp);
        return 1;
    }

    if ((size_t)file_size > 0 && fread(buffer, 1, (size_t)file_size, fp) != (size_t)file_size) {
        fprintf(stderr, "[replay] failed to read %s: %s\n", path, strerror(errno));
        free(buffer);
        fclose(fp);
        return 1;
    }
    fclose(fp);

    LLVMFuzzerTestOneInput(buffer, (size_t)file_size);
    free(buffer);

    files_processed += 1;
    if (files_processed % 1000 == 0) {
        fprintf(stderr, "[replay] processed %zu files\n", files_processed);
    }
    return 0;
}

static int replay_directory(const char *path) {
    DIR *dir = opendir(path);
    struct dirent *entry;

    if (dir == NULL) {
        fprintf(stderr, "[replay] failed to open directory %s: %s\n", path, strerror(errno));
        return 1;
    }

    while ((entry = readdir(dir)) != NULL) {
        char child_path[4096];

        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) {
            continue;
        }

        if (snprintf(child_path, sizeof(child_path), "%s/%s", path, entry->d_name) >= (int)sizeof(child_path)) {
            fprintf(stderr, "[replay] path too long under %s\n", path);
            closedir(dir);
            return 1;
        }

        if (replay_path(child_path) != 0) {
            closedir(dir);
            return 1;
        }
    }

    closedir(dir);
    return 0;
}

static int replay_path(const char *path) {
    struct stat st;

    if (stat(path, &st) != 0) {
        fprintf(stderr, "[replay] failed to stat %s: %s\n", path, strerror(errno));
        return 1;
    }

    if (S_ISDIR(st.st_mode)) {
        return replay_directory(path);
    }
    if (S_ISREG(st.st_mode)) {
        return replay_file(path);
    }
    return 0;
}

int main(int argc, char **argv) {
    int idx;

    if (argc < 2) {
        fprintf(stderr, "usage: %s <corpus path> [more corpus paths...]\n", argv[0]);
        return 2;
    }

    if (LLVMFuzzerInitialize(&argc, &argv) != 0) {
        fprintf(stderr, "[replay] LLVMFuzzerInitialize failed\n");
        return 1;
    }

    for (idx = 1; idx < argc; idx++) {
        if (replay_path(argv[idx]) != 0) {
            return 1;
        }
    }

    fprintf(stderr, "[replay] done, processed %zu files\n", files_processed);
    return 0;
}
