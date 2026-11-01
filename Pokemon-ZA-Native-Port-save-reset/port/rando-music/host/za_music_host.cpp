// Host CLI: create a COMPLETE randomizer run folder exactly as the r29-music title's New Run does (same core,
// progression, research rewards, trainer name, music step and the r29 run store), for PC proofs and tests.
//   za_music_host generate ASSETS REWARDS ROMFS_BIN PLAN.json OUT_ROOT SEED MODE(off|category|chaos) NAME
// ASSETS = ingame-randomizer/prepared-streamed, REWARDS = port/randomizer/reward-assets. Writes only OUT_ROOT.
// The run id is derived from the seed and mode so repeated invocations are comparable.
#include "progression.hpp"
#include "research_rewards.hpp"
#include "run_name.hpp"
#include "run_store.hpp"
#include "za_music.hpp"
#include <cstdio>
#include <string>

using namespace za;
using namespace za::native;

int main(int argc, char** argv) {
    if (argc != 10 || std::string(argv[1]) != "generate") {
        fprintf(stderr, "usage: %s generate ASSETS REWARDS ROMFS_BIN PLAN.json OUT_ROOT SEED MODE NAME\n", argv[0]);
        return 2;
    }
    const std::string assetsDir = argv[2], rewardsDir = argv[3], image = argv[4], planPath = argv[5], root = argv[6],
                      seed = argv[7], modeId = argv[8], name = argv[9];
    MusicMode mode;
    if (!parseMusicMode(modeId, mode)) return fprintf(stderr, "bad mode\n"), 2;
    auto reader = [&](const std::string& file, Bytes& data) {
        return readFile(assetsDir + "/" + file, data, 64u << 20) || readFile(rewardsDir + "/" + file, data, 64u << 20);
    };
    Bytes raw;
    auto json = [&](const std::string& file, Json& out) {
        if (!reader(file, raw)) return false;
        out = Json::parse(raw, nullptr, false);
        return !out.is_discarded() && out.is_object();
    };
    Json assets, starters, rewards, progression;
    if (!json("tables.json", assets) || !json("starter-deltas.json", starters) || !json("research-rewards.json", rewards) ||
        !json("progression.json", progression))
        return fprintf(stderr, "assets missing\n"), 1;
    Bytes planBytes;
    if (!readFile(planPath, planBytes, 4u << 20)) return fprintf(stderr, "plan missing\n"), 1;
    const std::string planText(planBytes.begin(), planBytes.end());
    assets["tables"]["research_rewards"] = {{"path", "ik_event/bin/research_lv/research_lv.bin"}};
    assets["tables"][MusicTableName] = {{"path", MusicBankPath}};
    Result result;
    std::string error;
    Options options;
    if (!generate(assets, starters, reader, seed, options, 0, result)) return fprintf(stderr, "generate: %s\n", result.error.c_str()), 1;
    result.report["options"]["research_rewards"] = true;
    if (!protectProgression(progression, reader, seed, result, error) || !randomizeResearchRewards(rewards, reader, seed, result, error) ||
        !nameRun(name, result, error) ||
        !randomizeMusic(planText, [&](const Json& plan, Bytes& bank) { return readBankFromRomfs(image, plan, bank); }, seed, mode, result, error))
        return fprintf(stderr, "step: %s\n", error.c_str()), 1;
    const std::string tag = seed + "|" + modeId;
    const std::string digest = sha256(Bytes(tag.begin(), tag.end()));
    const std::string id = "r" + digest.substr(0, 16) + "-" + digest.substr(16, 8);
    if (!publishRun(root, id, assets, result, error)) return fprintf(stderr, "publish: %s\n", error.c_str()), 1;
    printf("%s\n", id.c_str());
    return 0;
}
