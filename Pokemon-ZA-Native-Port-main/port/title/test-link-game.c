/* Link audit only. Never package/deploy this image; no game is present. */
#include "gamelib.h"
const GameLibTables *lasgame_tables(void) { return 0; }
