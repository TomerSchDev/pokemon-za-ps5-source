#pragma once
// The music plan compiled into the title. za_music_plan.cpp is GENERATED at build time by tools/embed_plan.py from
// the plan that tools/make_music_plan.py derives from the game's own BGM.bnk; it is game-derived and never in git.
namespace za::native {
const char* zaMusicPlanJson();    // the plan text (JSON), NUL-terminated
const char* zaMusicPlanSha256();  // SHA-256 of that text, fixed when it was generated
}
