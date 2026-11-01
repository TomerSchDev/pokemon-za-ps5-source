// ui-v2: the CURRENT look, rendered by copies of the real drawing code, for side-by-side comparison.
//
// LegacyDisplay reproduces za::native::Display (port/randomizer/menu_display.cpp): a 1280x720 logical canvas whose
// rect() multiplies every coordinate by 3/2 into the 1920x1080 VideoOut buffer (that is where the uneven 4/5-pixel
// glyph blocks come from), the 5x7 bitmap font of menu_font.h (included by path, not copied) and the exact page
// layouts of port/rando-music/native_menu_music.cpp. The only difference is a linear buffer instead of the tiled one.
//
// LegacyVk reproduces the cheats overlay (port/perf-r28/src/cheats-r28.cpp): vkCmdClearAttachments rectangles mapped
// from 1280x720 onto the 3840x2160 swapchain (x * w / 1280), no alpha, then box-filtered to 1920x1080 for the PNG.
#pragma once
#include "ui_canvas.h"

namespace ui::legacy {

// Current launcher: main page (12 rows, NAME and MUSIC included), seed keypad, saved runs. Output is 1920x1080.
void launcherMain(Canvas& out);
void launcherSeed(Canvas& out);
void launcherSaved(Canvas& out);

// Current overlay over `background` (1920x1080): page 1 (cheats) and page 2 (ITEMS / AMOUNT / ADD ITEM rows).
void overlayPage1(Canvas& out, const Canvas& background);
void overlayPage2(Canvas& out, const Canvas& background);

}  // namespace ui::legacy
