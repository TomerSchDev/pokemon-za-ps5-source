#include "run_name.hpp"
#include "run_store.hpp"
#include "za_player_name.hpp"

#include <cerrno>
#include <cstdio>
#include <fcntl.h>
#include <unistd.h>

namespace za::native {
bool nameRun(const std::string& name, Result& result, std::string& error) {
    if (!result.report.is_object()) { error = "Run report is not an object"; return false; }
    PlayerNameEdit edit;
    std::string why;
    if (!applyPlayerName(result.save, name, edit, why)) {
        error = "Trainer name could not be written: " + why;
        return false;
    }
    result.report["player_name"] = name;
    result.report["player_name_algorithm"] = PlayerNameAlgorithm;
    result.report["player_name_template"] = edit.oldName;
    result.report["player_name_pokemon"] = {{"renamed", edit.pokemonRenamed}, {"kept", edit.pokemonKept},
                                             {"unreadable", edit.pokemonUnreadable}};
    result.report["save_sha256"] = sha256(result.save);
    return true;
}

std::string reportPlayerName(const Json& report) {
    if (!report.is_object() || !report.contains("player_name") || !report["player_name"].is_string()) return {};
    const auto name = report["player_name"].get<std::string>();
    return validPlayerName(name) ? name : std::string{};
}

bool replayRunName(const Json& report, Result& result, std::string& error) {
    if (!report.is_object()) { error = "Source run report is not an object"; return false; }
    if (!report.contains("player_name")) {
        if (report.contains("player_name_algorithm")) { error = "Source trainer name is missing"; return false; }
        return true;
    }
    const auto name = reportPlayerName(report);
    if (name.empty()) { error = "Source trainer name is invalid"; return false; }
    // Reports from the offline rando-v2 prototype predate the algorithm marker.
    if (report.contains("player_name_algorithm") &&
        (!report["player_name_algorithm"].is_string() || report["player_name_algorithm"] != PlayerNameAlgorithm)) {
        error = "Source trainer name algorithm is unsupported";
        return false;
    }
    return nameRun(name, result, error);
}

std::string rememberedPlayerName(const std::string& root) {
    Bytes bytes;
    if (!readFile(root + "/player-name.txt", bytes, 64)) return {};
    std::string name(bytes.begin(), bytes.end());
    while (!name.empty() && (name.back() == '\n' || name.back() == '\r')) name.pop_back();
    return validPlayerName(name) ? name : std::string{};
}

bool rememberPlayerName(const std::string& root, const std::string& name) {
    if (!validPlayerName(name)) return false;
    const std::string path = root + "/player-name.txt", temp = path + ".new", line = name + "\n";
    // Only clear our private staging path. Exclusive creation also refuses a
    // concurrent writer or symlink instead of following/truncating it.
    if (unlink(temp.c_str()) && errno != ENOENT) return false;
    const int fd = open(temp.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0644);
    if (fd < 0) return false;
    size_t at = 0;
    bool ok = true;
    while (at < line.size()) {
        const ssize_t n = write(fd, line.data() + at, line.size() - at);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { ok = false; break; }
        at += size_t(n);
    }
    if (ok && fsync(fd)) ok = false;
    if (close(fd)) ok = false;
    Bytes check;
    ok = ok && readFile(temp, check, 64) && std::string(check.begin(), check.end()) == line;
    if (ok && rename(temp.c_str(), path.c_str())) ok = false;
    if (!ok) { unlink(temp.c_str()); return false; }
    // Match run_store's tolerated PS5 directory-fsync limitations. File fsync
    // and atomic rename above are mandatory even on these filesystems.
    const int dir = open(root.c_str(), O_RDONLY);
    if (dir < 0) return errno == EPERM || errno == ENOTSUP;
    const int rc = fsync(dir), saved = errno;
    close(dir);
    return !rc || saved == EINVAL || saved == ENOTSUP || saved == EPERM;
}
}
