// Check the public JSON parser against the independently consumed build-time release contract.
// No game assets are required: launcher-owned defaults must pass through; generator tiers must match the contract.
#include "rando_v3.hpp"
#include <fstream>
#include <iostream>

using namespace za;
using namespace za::v3;
#define CHECK(x) do { if (!(x)) { std::cerr << "CHECK failed: " #x " at line " << __LINE__ << "\n"; return 1; } } while (0)

int main(int argc, char** argv) {
    if (argc != 2) { std::cerr << "usage: test_ui_contract CAPABILITIES\n"; return 2; }
    std::ifstream file(argv[1]);
    CHECK(file.good());
    Json caps = Json::parse(file, nullptr, false);
    CHECK(caps.is_object());
    int accepted = 0, rejected = 0;
    for (const char* section : {"options", "proposed_options"})
        for (const auto& [key, row] : caps.at(section).items()) {
            auto verify = [&](const Json& id, bool expected) {
                Settings settings; std::string error;
                bool ok = settingsFromUi(Json{{"schema", 2}, {"values", {{key, id}}}}, settings, error);
                if (ok) accepted++; else rejected++;
                if (ok != expected || (!expected && error.find(key) == std::string::npos)) {
                    std::cerr << "contract mismatch: " << key << "=" << id << " expected=" << expected << " error=" << error << "\n";
                    return false;
                }
                return true;
            };
            if (row.contains("supported") && row["supported"].is_array())
                for (const auto& id : row["supported"]) CHECK(verify(id, true));
            if (row.contains("unsupported"))
                for (const auto& id : row["unsupported"]) CHECK(verify(id, false));
            if (row.contains("options"))
                for (const auto& id : row["options"]) {
                    bool supported = false;
                    for (const auto& supportedId : row.at("supported")) supported |= id == supportedId;
                    CHECK(verify(id, supported));
                }
        }
    Settings settings; std::string error;
    // The generator ignores these values; the launcher validates/executes them and keeps them in ui_options.
    for (const char* shiny : {"normal", "x4", "x16", "x64", "always"})
        for (const char* capture : {"normal", "x2", "x4", "x8", "max"}) {
            CHECK(settingsFromUi(Json{{"schema", 2}, {"values", {{"shiny_default", shiny}, {"capture_default", capture},
                {"music", "chaos"}, {"player_name", "Tomer"}, {"future_option", "retained by the caller"}}}}, settings, error));
            CHECK(settingsToUi(settings) == settingsToUi(Settings{}));
            accepted++;
        }
    CHECK(!settingsFromUi(Json{{"schema", 2}, {"values", {{"wild_levels", "unknown"}}}}, settings, error));
    CHECK(!settingsFromUi(Json{{"schema", 2}, {"values", {{"alpha_rate", 5}}}}, settings, error));
    CHECK(!settingsFromUi(Json{{"schema", 2}, {"values", {{"starter_level", 8}}}}, settings, error));
    CHECK(!settingsFromUi(Json{{"schema", 1}, {"values", Json::object()}}, settings, error));
    std::cout << "PASS: UI contract " << accepted << " accepted, " << rejected + 4 << " rejected; 25 launcher-default combinations unchanged\n";
}
