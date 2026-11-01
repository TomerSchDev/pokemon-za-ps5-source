include Makefile

# New targets avoid changing prerequisites already expanded in the upstream
# Makefile. Generated code uses the identical flags and ABI id as ps5-gamelib.
TITLE_BACKEND := $(filter-out $(B)/rt/nvn/vulkan/imgui_glue.o,$(BACKEND_OBJ))
TITLE_OBJS := $(RT_OBJ) $(TITLE_BACKEND)
$(B)/rt/main.o: RTFLAGS += -Dmain=za_game_main
.PHONY: offline-runtime offline-title offline-link-smoke
offline-runtime: $(TITLE_OBJS)
offline-link-smoke: $(TITLE_OBJS)
	@mkdir -p $(B)/smoke
	$(CC) $(RTFLAGS) -c $(TITLE_TEST_SOURCE) -o $(B)/smoke/test-link-game.o
	bash tools/ps5/link-title.sh $(B)/smoke/llvm-pie.elf $(TITLE_OBJS) $(B)/smoke/test-link-game.o
offline-title: $(TITLE_OBJS) $(GAMELIB)
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) $(GAMELIB)
