// ui-v2 design tokens: palette, type scale and spacing for a 1920x1080 canvas.
// The brand colours of the current menus are kept (teal accent on deep navy); everything else is new.
#pragma once
#include "ui_canvas.h"

namespace ui::theme {

// Palette
constexpr Color Bg0 = rgb(0x0B1524);        // page background, top
constexpr Color Bg1 = rgb(0x0F1D2E);        // page background, bottom
constexpr Color Panel = rgb(0x132236);      // cards, panels
constexpr Color PanelEdge = rgb(0x24364F);  // 1 px borders
constexpr Color Row = rgb(0x172A3F);        // unfocused interactive row
constexpr Color RowFocus = rgb(0x1C3F3B);   // focused row (teal tint)
constexpr Color Accent = rgb(0x54E3AA);     // focus bar, selected values, primary actions
constexpr Color AccentInk = rgb(0x06261B);  // text on an accent-filled pill
constexpr Color AccentDim = rgb(0x2C7D62);  // level dots, inactive accent
constexpr Color Text = rgb(0xEDF5FC);
constexpr Color Text2 = rgb(0x9FB2C7);      // descriptions, secondary
constexpr Color Text3 = rgb(0x6A7E95);      // hints, disabled
constexpr Color Warn = rgb(0xFFCE80);       // "not in this build", queued
constexpr Color Err = rgb(0xFF8F7E);        // failures, pocket full
constexpr Color Ok = Accent;
constexpr Color Info = rgb(0x7FB7FF);
constexpr Color Shadow = rgb(0x000000, 110);
constexpr Color OverlayBg = rgb(0x0C1726, 232);  // translucent in-game panel
constexpr Color OverlayEdge = rgb(0x2E4360, 255);
constexpr Color Scrim = rgb(0x000000, 70);       // dims the game behind the overlay

// Type scale (em sizes in pixels at 1080p)
constexpr float TitleSize = 24;    // "POKÉMON LEGENDS Z-A · RANDOMIZER"
constexpr float SeedSize = 44;     // the seed in the header chip
constexpr float SeedBigSize = 72;  // the seed on the seed screen / confirm
constexpr float H1Size = 34;       // page title
constexpr float RowSize = 27;      // row label
constexpr float ValueSize = 24;    // value pill
constexpr float DescSize = 20;     // descriptions
constexpr float HintSize = 20;     // footer hints
constexpr float SmallSize = 17;    // badges, meta
constexpr float NavSize = 24;      // nav labels
constexpr float NavSubSize = 17;   // nav value summary

// Spacing (8 px grid)
constexpr float Margin = 96;       // left/right page margin
constexpr float Top = 36;          // header top
constexpr float HeaderH = 112;
constexpr float NavW = 384;
constexpr float NavGap = 40;
constexpr float RowH = 92;         // settings row (label + description)
constexpr float RowGap = 6;
constexpr float RowRadius = 14;
constexpr float PillH = 44;
constexpr float PillRadius = 22;
constexpr float FooterH = 76;
constexpr float ListRowH = 58;     // item picker rows
constexpr int ListVisible = 10;

}  // namespace ui::theme
