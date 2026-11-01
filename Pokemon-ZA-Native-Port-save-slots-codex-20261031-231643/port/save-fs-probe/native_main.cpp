#include "demo_renderer.hpp"  // existing native-probe renderer, unchanged
#include "fs_probe.hpp"
namespace {
void draw(ps5::demo::Canvas& canvas) noexcept {
    using ps5::demo::Color;
    canvas.clear(Color::background);
    canvas.text(100, 160, "ZA SAVE FS API PROBE", 8, Color::white);
    canvas.text(100, 340, za::save_fs_probe::summary(), 4, Color::cyan);
    canvas.text(100, 500, "PRIVATE SYNTHETIC FILES ONLY", 4, Color::yellow);
    canvas.text(100, 620, "NO GAME OR SAVE DATA ACCESSED", 4, Color::white);
}
}
int main() {
    za::save_fs_probe::run();
    ps5::demo::run(draw, "Save filesystem API observations");
}
