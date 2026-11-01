// Regression for the exact PS5 scan_number assertion, including the frozen
// metadata corpus. The driver also builds two deliberately broken controls.
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <locale.h>
#include <thread>
#include <vector>

using Json = nlohmann::json;
static int failures;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); ++failures; } } while (0)

int main(int argc, char **argv) {
    const Json probe = Json::parse("{\"alpha\":0.62}", nullptr, false);
    CHECK(!probe.is_discarded() && probe["alpha"] == 0.62);
    if (argc == 2 && !std::strcmp(argv[1], "--probe")) return failures ? 1 : 0;
    CHECK(argc == 2);
    if (argc != 2) return 2;
    const struct { const char *text; double expected; } vectors[] = {
        {"0.0", 0.0}, {"-0.0", -0.0}, {"0.62", 0.62}, {"12.5", 12.5},
        {"-25.75", -25.75}, {"1.25e2", 125.0}, {"6.25E-2", 0.0625},
        {"100.0", 100.0}, {"18446744073709551616", 18446744073709551616.0},
        {"10000000000000000000000000000000000000000", 1e40},
    };
    for (const auto& v : vectors) {
        const Json j = Json::parse(v.text, nullptr, false);
        CHECK(!j.is_discarded() && j.is_number() && j.get<double>() == v.expected);
        if (!std::strcmp(v.text, "-0.0")) CHECK(std::signbit(j.get<double>()));
    }
    for (const char *invalid : {"1.", ".5", "01", "1e", "1e+", "NaN", "Infinity", "1e9999"})
        CHECK(Json::parse(invalid, nullptr, false).is_discarded());
    const Json underflow = Json::parse("1e-9999", nullptr, false);
    CHECK(!underflow.is_discarded() && underflow == 0.0);
    char *end = nullptr;
    errno = 0;
    const char text[] = " \t-12.5tail";
    CHECK(std::strtod(text, &end) == -12.5 && end == text + 7 && !errno);
    const char bad[] = "xyz";
    CHECK(std::strtod(bad, &end) == 0.0 && end == bad);
    errno = 0;
    CHECK(std::isinf(std::strtod("1e9999", &end)));
    CHECK(errno == ERANGE && end && !*end);
    std::fprintf(stderr, "range errno: overflow=%d", errno);
    errno = 0;
    CHECK(std::strtod("1e-9999", &end) == 0.0);
    CHECK(errno == ERANGE && end && !*end);
    std::fprintf(stderr, " underflow=%d\n", errno);
    auto threaded = [] {
        for (int i = 0; i < 1000; ++i) {
            const lconv *lc = localeconv();
            if (!lc || !lc->decimal_point || std::strcmp(lc->decimal_point, ".") ||
                Json::parse("-1.25e-2").get<double>() != -0.0125) std::abort();
        }
    };
    std::thread one(threaded), two(threaded);
    one.join(); two.join();
    std::vector<std::filesystem::path> files;
    for (const auto& e : std::filesystem::directory_iterator(argv[1]))
        if (e.path().extension() == ".json") files.push_back(e.path());
    std::sort(files.begin(), files.end());
    uint64_t hash = UINT64_C(14695981039346656037);
    size_t floats = 0;
    for (const auto& path : files) {
        std::ifstream in(path);
        const Json doc = Json::parse(in, nullptr, false);
        CHECK(!doc.is_discarded());
        const auto visit = [&](const auto& self, const Json& value) -> void {
            if (value.is_number_float()) ++floats;
            if (value.is_structured()) for (const auto& child : value) self(self, child);
        };
        visit(visit, doc);
        for (unsigned char c : path.filename().string() + "\n" + doc.dump()) { hash ^= c; hash *= UINT64_C(1099511628211); }
    }
    std::printf("files=%zu floats=%zu canonical_fnv64=%016llx\n", files.size(), floats, (unsigned long long)hash);
    return failures ? 1 : 0;
}
