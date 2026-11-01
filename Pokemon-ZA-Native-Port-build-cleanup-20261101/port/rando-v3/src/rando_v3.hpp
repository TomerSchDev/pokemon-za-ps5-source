// rando-v3: the tiered randomization levels of UI v2 (port/ui-v2/src/ui_model.cpp) on top of the unchanged r15 core.
//
// One generator call produces every table of a run (wild, trainers, dlc_boss, research_rewards, optional personal)
// plus the starting save, from a seed and a Settings struct that is decoded from report.json's "ui_options". With
// the default settings (wild_mode=random, trainers_mode=random, megas on, DLC rematches on, research rewards on)
// the tables are byte-identical to today's pipeline (core generate -> protectProgression -> randomizeResearchRewards);
// the host tests prove that for 100+ seeds. No filesystem writes, no game/console APIs in this module.
#pragma once
#include "randomizer.hpp"

namespace za::v3 {
enum class WildMode { Off, Zones, InZone, Random, Chaos };
enum class WildLevels { Vanilla, Plus10, Plus25, Range, Mixed };
enum class AlphaRate { Vanilla, X2, X5, Always };
enum class Forms { Vanilla, Random };
enum class TrainersMode { Off, Swap, Strength, Random };
enum class TrainerLevels { Vanilla, Plus10, Plus20, Plus30 };
enum class TrainerMoves { Learnset, Legal, Any };
enum class TrainerItems { Vanilla, Random, None };
enum class ResearchRequirements { Vanilla, Easier, Harder };
enum class BaseStats { Vanilla, Shuffle, Random };
enum class CatchRate { Vanilla, X2, Max };

struct Settings {
    WildMode wild = WildMode::Random;
    WildLevels wildLevels = WildLevels::Vanilla;
    AlphaRate alpha = AlphaRate::Vanilla;
    Forms forms = Forms::Vanilla;
    TrainersMode trainers = TrainersMode::Random;
    bool megaTrainers = true, dlcRematches = true;
    TrainerLevels trainerLevels = TrainerLevels::Vanilla;
    TrainerMoves trainerMoves = TrainerMoves::Learnset;
    TrainerItems trainerItems = TrainerItems::Vanilla;
    int starter = 0;  // species of the validated city-starter pool; 0 = the seed decides (today's "Random from seed")
    bool researchRewards = true;
    ResearchRequirements researchRequirements = ResearchRequirements::Vanilla;
    BaseStats baseStats = BaseStats::Vanilla;
    CatchRate catchRate = CatchRate::Vanilla;
};

// "ui_options" ({"schema": 2, "values": {...}}, or just the values object) -> Settings. Missing keys keep the
// defaults; keys the generator does not own (music, player_name, cheat defaults, ...) and unknown keys are ignored;
// an option id this build does not implement (wild_mega_rate != vanilla, held_items != vanilla, starter_level != 7,
// an unknown level id) fails with a message naming it, so a run is never created with a setting it will not have.
bool settingsFromUi(const Json& uiOptions, Settings& out, std::string& error);
// The resolved settings as a schema-2 values object (what the run will actually do), written to the report.
Json settingsToUi(const Settings& s);
// Today's launcher toggles -> Settings (for callers that still build Options).
Settings settingsFromLegacy(const Options& options, bool researchRewards, int starter);
// Legacy booleans of a Settings (report "options" and anything that still reads them).
Options legacyOptions(const Settings& s);

struct Assets {
    Json tables;       // tables.json (schema 1, za202-randomizer-alpha1)
    Json starters;     // starter-deltas.json
    Json progression;  // progression.json (schema 4, za202-story-guard-v2)
    Json rewards;      // research-rewards.json (schema 3)
    Json v3;           // v3.json (za-rando-v3-1)
};

// uiOptionsEcho is stored in the report as "ui_options" exactly as received (may be null for legacy callers).
bool generateRun(const Assets& assets, const Reader& read, const std::string& seed, const Settings& settings,
                 const Json& uiOptionsEcho, Result& out, const Progress& progress = {});

// Table names generateRun may produce beyond today's four (recorded by run_store_v3 under "native_extra_tables").
constexpr const char* PersonalTable = "personal";
constexpr const char* Algorithm = "za202-randomizer-v3";
}  // namespace za::v3
