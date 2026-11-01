/* Fixed-title metadata update. Uses SQLite's locking and backup API, never
 * replaces app.db or uninstalls/re-registers a title. */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "sqlite3.h"

#ifndef ZA_DB_PATH
#define ZA_DB_PATH "/system_data/priv/mms/app.db"
#define ZA_DB_BACKUP "/data/za-branding-r13-appdb-before.sqlite"
#define ZA_RENAME_LOG "/data/za-branding-r13-rename.log"
#endif

int main(void) {
    sqlite3 *db=NULL,*copy=NULL; sqlite3_stmt *q=NULL; sqlite3_backup *b=NULL;
    int rc=1, in_transaction=0;
    FILE *log=fopen(ZA_RENAME_LOG,"w"); if (!log) return 1;
    setvbuf(log,NULL,_IONBF,0);
    if (sqlite3_open_v2(ZA_DB_PATH,&db,SQLITE_OPEN_READWRITE,NULL)!=SQLITE_OK) goto fail;
    sqlite3_busy_timeout(db,1000);
    if (sqlite3_prepare_v2(db,"SELECT titleName FROM tbl_contentinfo WHERE titleId='PPSA91761'",-1,&q,NULL)!=SQLITE_OK) goto fail;
    if (sqlite3_step(q)!=SQLITE_ROW) goto fail;
    const char *name=(const char*)sqlite3_column_text(q,0);
    if (name && !strcmp(name,"Pok\xc3\xa9mon Legends: Z-A")) {
        fprintf(log,"Already named correctly; no change\n"); rc=0; goto done;
    }
    if (!name || strcmp(name,"ZA Native Title R2 (Test)")) goto fail;
    fprintf(log,"Verified old name: %s\n",name);
    sqlite3_finalize(q); q=NULL;
    /* Never overwrite an existing backup from another attempt. */
    if (access(ZA_DB_BACKUP,F_OK)==0) { fprintf(log,"Backup exists; refusing a second transaction\n"); goto done; }
    if (sqlite3_open_v2(ZA_DB_BACKUP,&copy,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE,NULL)!=SQLITE_OK) goto fail;
    b=sqlite3_backup_init(copy,"main",db,"main"); if(!b) goto fail;
    int step=sqlite3_backup_step(b,-1);
    int finish=sqlite3_backup_finish(b); b=NULL;
    if(step!=SQLITE_DONE || finish!=SQLITE_OK) goto fail;
    if(sqlite3_close(copy)!=SQLITE_OK) goto fail; copy=NULL;
    fprintf(log,"Consistent pre-update database backup completed\n");
    if(sqlite3_exec(db,"BEGIN IMMEDIATE",NULL,NULL,NULL)!=SQLITE_OK) goto fail;
    in_transaction=1;
    const char *sql="UPDATE tbl_contentinfo SET titleName=?1, AppInfoJson=json_set(AppInfoJson,'$.TITLE',?1,'$.TITLE_01',?1) "
                    "WHERE titleId='PPSA91761' AND titleName='ZA Native Title R2 (Test)' AND json_valid(AppInfoJson)";
    if(sqlite3_prepare_v2(db,sql,-1,&q,NULL)!=SQLITE_OK) goto fail;
    sqlite3_bind_text(q,1,"Pok\xc3\xa9mon Legends: Z-A",-1,SQLITE_STATIC);
    if(sqlite3_step(q)!=SQLITE_DONE || sqlite3_changes(db)!=1) goto fail;
    sqlite3_finalize(q); q=NULL;
    if(sqlite3_exec(db,"COMMIT",NULL,NULL,NULL)!=SQLITE_OK) goto fail;
    in_transaction=0;
    fprintf(log,"COMMIT: exactly one title row renamed; IDs and save data unchanged\n"); rc=0; goto done;
fail:
    fprintf(log,"FAILED: %s\n",db?sqlite3_errmsg(db):"no database");
done:
    if(q) sqlite3_finalize(q);
    if(b) sqlite3_backup_finish(b);
    if(in_transaction) sqlite3_exec(db,"ROLLBACK",NULL,NULL,NULL);
    if(copy) sqlite3_close(copy);
    if(db) sqlite3_close(db);
    fclose(log); return rc;
}
