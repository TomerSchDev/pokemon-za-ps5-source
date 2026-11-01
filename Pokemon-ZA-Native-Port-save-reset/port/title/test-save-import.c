#define _GNU_SOURCE 1
#include <assert.h>
#include "save_import.h"

int main(void) {
    char root[] = "/tmp/za-save-import-XXXXXX";
    assert(mkdtemp(root));
    char source[1024], dir[1024], path[1024];
    assert(!za_save_path(source, root, "source"));
    assert(!za_save_write_new(source, (const unsigned char *)"abc", 3));
    assert(!za_save_path(dir, root, "save/save_0"));
    assert(!za_save_dirs(dir));
    assert(!za_save_path(path, dir, "main"));
    assert(!za_save_write_new(path, (const unsigned char *)"old-progress", 12));
    /* Corrupt/unexpected input must not touch existing progress. */
    assert(za_import_save_once(source, dir, "test", 3, 0) == -1);
    assert(za_save_matches(path, (const unsigned char *)"old-progress", 12));
    assert(za_import_save_once(source, dir, "test", 3, UINT64_C(0xe71fa2190541574b)) == 1);
    assert(za_save_matches(path, (const unsigned char *)"abc", 3));
    char backup[1024]; assert(!za_save_path(backup, dir, "main.before-test"));
    assert(za_save_matches(backup, (const unsigned char *)"old-progress", 12));
    /* A subsequent game save must survive every later startup. */
    FILE *f = fopen(path, "wb"); assert(f);
    assert(fwrite("later-progress", 1, 14, f) == 14 && !fclose(f));
    assert(za_import_save_once(source, dir, "test", 3, UINT64_C(0xe71fa2190541574b)) == 0);
    assert(za_save_matches(path, (const unsigned char *)"later-progress", 14));
    /* Simulated interrupted transaction cannot be retried blindly. */
    char journal[1024]; assert(!za_save_path(journal, dir, ".import-interrupted.in-progress"));
    assert(!za_save_write_new(journal, (const unsigned char *)"interrupted", 11));
    assert(za_import_save_once(source, dir, "interrupted", 3, UINT64_C(0xe71fa2190541574b)) == -1);
    assert(za_save_matches(path, (const unsigned char *)"later-progress", 14));
    /* A partial completion marker also blocks rather than discarding progress. */
    char marker[1024]; assert(!za_save_path(marker, dir, ".import-partial.done"));
    assert(!za_save_write_new(marker, (const unsigned char *)"par", 3));
    assert(za_import_save_once(source, dir, "partial", 3, UINT64_C(0xe71fa2190541574b)) == -1);
    assert(za_save_matches(path, (const unsigned char *)"later-progress", 14));
    puts("save import: corrupt-source rejection, backup, readback, idempotence, interrupted/partial-marker protection passed");
    return 0;
}
