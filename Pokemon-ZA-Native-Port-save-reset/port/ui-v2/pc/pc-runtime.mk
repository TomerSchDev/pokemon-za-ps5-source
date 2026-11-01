# pc-runtime.mk - the Windows runtime objects WITHOUT the Dear ImGui UI (runtime/ui/*.mm, third_party/imgui and
# nvn/vulkan/imgui_glue.o are left out), the way port/title/offline-title.mk builds the PS5 title: `include Makefile`
# plus new targets only, so every flag (RTFLAGS, OSFLAGS, CXXFLAGS, LDFLAGS, GAMELIB_CFLAGS, the windres rule) is the
# upstream Makefile's. The UI symbols the runtime calls are supplied by the exe's entry object (pc_entry_stub.c lists
# them). Run from a COPY of the runtime source tree, never inside the repo (port/ui-v2/pc/build-pc-runtime.sh puts the
# copy in ui-v2-work/pc/src and runs this), e.g.
#   make -f pc-runtime.mk -j16 PLATFORM=windows GAMELIB_ID=7b03da558e0b6144 DEPS=../deps/sdl3 B=build pc-objects
# GAMELIB_ID on the command line overrides the Makefile's computed hash (the reference PC game DLL's id is
# 7b03da558e0b6144); DEPS points at the SDL3 3.4.x headers + import library (MSYS2's SDL3 is 3.2.x: no SDL_SavePNG).
include Makefile

PC_BACKEND_OBJ := $(filter-out $(B)/rt/nvn/vulkan/imgui_glue.o,$(BACKEND_OBJ))
PC_OBJS := $(RT_OBJ) $(PC_BACKEND_OBJ)

# RT_MAIN_SYMBOL=<name>: compile runtime/main.c's main() under another name, so an entry of your own can run first and
# call it (the PS5 title does this with za_game_main). Empty (default): main() stays the exe's entry point.
ifneq ($(strip $(RT_MAIN_SYMBOL)),)
$(B)/rt/main.o: RTFLAGS += -Dmain=$(RT_MAIN_SYMBOL)
endif

.PHONY: pc-objects pc-print-rtflags pc-print-cxxflags pc-print-ldflags pc-print-genflags pc-print-gamelib-id pc-print-objects
pc-objects: $(PC_OBJS)
	@mkdir -p $(B)
	@printf '%s\n' $(PC_OBJS) > $(B)/pc-objects.txt
	@echo "pc-objects: $(words $(PC_OBJS)) objects listed in $(B)/pc-objects.txt"
pc-print-rtflags: ; @echo '$(RTFLAGS)'
pc-print-cxxflags: ; @echo '$(CXXFLAGS) $(OSFLAGS)'
pc-print-ldflags: ; @echo '$(LDFLAGS)'
pc-print-genflags: ; @echo '$(GENFLAGS)'
pc-print-gamelib-id: ; @echo '$(GAMELIB_ID)'
pc-print-objects: ; @printf '%s\n' $(PC_OBJS)
