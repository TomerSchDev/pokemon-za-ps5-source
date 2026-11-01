# Card: Z-A Unity prototype (Windows development)

Read the complete repository AGENTS.md and `zw card rules` first.

## Existing tools
- `zw unity-build -Output <new absolute Windows folder>` calls the existing Unity Build.ps1.
- `zw unity run_player_checks --player <exe> --out <new QA folder>` uses isolated prototype saves.
- `zw unity render_demo --player <exe> --frames <new folder> --out <new mp4> --progress-tour` records actual offline game frames.
- `zw unity package_release --build <folder> --qa <folder> --out <new local release folder> --version <version>` verifies and packages locally.
- `zw unity-content catalog export|validate ...` uses the existing converted-model catalog.
- `zw unity-visuals <script> ...` forwards existing Tools/visuals scripts.
These forwards use the Unity project's existing Python environment and working directory; they do not contact a console.

## Known facts
- ASCII project junction: C:/Users/Tomer/Documents/ChatGPT/Pokemon-ZA-Unity; original workspace remains under פריצות.
- Unity 6000.6.7f1 / URP17.6.0; Windows Mono/D3D11 is verified. This is not a tested PS5 Unity build.
- v0.12.0 passed135 rendered-player checks; its model catalog has393 models (12 Pokemon,2 humans,1 prop,378 environment models).
- Native geometry/UV0/weights for Pikachu+Trainer match converted data; inverse-bind differences are float precision only. Work/GeometryAudit records numerical proof.
- Generic URP/Lit character materials remain a rendering approximation; native material fidelity is under investigation. Imported geometry alone does not prove original visual style.
- Existing palette/normal GLSL308064 and alpha4f7a14 are code/SHA-linked to the native ik_character BNSH family (10 variation descriptors checked); material-specific variants and texture bindings remain unproven. Local Work/CodeAudit/ShaderResearch/LINKED-IKCHARACTER.md records evidence.
- User requested local source/build packages; update videos are also copied to NAS Video-Updates with SHA-256 verification. Never upload raw game data, saves or keys.
- Source/PC research notes and captures stay local; use a new output folder and preserve user progress.
- FullSurfaceRetention-v3 locally retains20 Pikachu/Trainer materials and207 TRMTR bindings to proven Linked-v20 semantics (aliases9/11/12); payloads matchv2, actual image/variation/UV/draw selection remains unproven.
- v0.13 r11 Windows player passed150 checks (QA/v013-probe-r11-20261031);20 Pikachu/Trainer source-channel probe profiles compile/render, but native material variation/UV fidelity remains unproven.
- Mesh CopySerialized retained the old vertex layout (tangents33→0); explicit channel copy preserves source tangents/UVs, and all12 Pokemon retain tangent channels across their four LODs in the built r11 player.
- v0.14 r3 Windows player passed152 checks;600-frame ground A/B verifies fixed pose/light/camera, original512px normal maps and5123 source ground tangents. Roughness remains unmapped; Native Standard rendering/UV roles are not fully proved.
- Original initializer7000ea41a0 explicitly sets151 vector defaults (not BSS): UVCenter1=(.5,.5,0,0), UVScaleOffset1=(1,1,0,0), EmissionColorLayer5=(0,0,0,1); Work/CodeAudit/ShaderResearch/VECTOR-DEFAULTS.md.
- v0.15 r1 passed154 Windows-player checks and600-frame Pikachu source-base A/B;4body materials use independent verified source base/masks and sampler1Repeat/6Mirror; active native variation/full lighting remain unproven.
- Coverage-v3 inventories393models/3096materials/77shader+flag families/10028map bindings/1533native paths; CatalogSourceRetention-v1 retains1892SHA-verifiedBNTX/TRMTRobjects and authored mips locally. This is source coverage, not completed Unity rendering.
- SamplerWrap-v07 proves TRMTR fields9/10/11 pass unchanged to NVN U/V/W; current PC backends map1Repeat/6Mirror/0or7ClampToEdge; original hardware is untested.
- SamplerWrapInventory-v1 independently checks all2639 active city BaseColor bindings: ordinal0/converted fields agree,2637 use1/1 and2 use7/7; corrected PNG-SHA+wrap sharing predicts381 keys instead of515 (Work/VisualFidelity).
- Native uniform7/PC CB10:1850bb0 builds four vectors from object+a0 through008e4c0 with optional composition;288-byte upload unchanged is proved, selected draw/world-view space unresolved (FrameOwner-v02).
- v0.16 r4 passed157 rendered-player checks:116 Standard models retain1674413 tangents/182mesh-LODs;850 added normal materials+2 existing ground,2639 city base bindings share381 verified textures. Native UV/lighting remains a controlled probe.
- RTX3050/D3D11 nativeBC4/5 experiment audits39 authored mips;768 sampled floats match NVIDIA UNORM16 decode bit-exact, explaining PNG8-floor residual; no original-framebuffer/globalUV parity (GroundGpuResidual-v3).
- All23 compatible body materials initialize ReceiveShadow1/Category6/ShadowStrength.7; typed intCategory6→float6→scalar156 is proven. Active instance/world/shadow-image owners remain open (CategoryLabel-v03/InputAdapter-v07).
- v0.17 r4 passed159 rendered-player checks;23 source-color body materials across9 native Pokemon use46 Base/Mask bindings/30 independent texture contracts.900-frame three-group A/B fixes native Idle25%,light/camera/non-base state;19 added bodies remain normal/highlight/discard-off, original20 profiles unchanged.
- PreviewV3 compares full serialized prefab semantics using stable hierarchy/asset references; skips raw PPtr children/localIDs while retaining prefab GUID/meta and other dependency SHAs. Native prefab regeneration changes local fileIDs without changing reviewed structure.
- v0.18 r1 passed161 rendered-player checks:23 bodies/9 Pokemon use a separate matte lighting adapter with46 original Normal/AO bindings/28 linear image+wrap contracts.900-frame A/B changes only _NativeLightingMode; source base stays ON. Native normal/HalfLambert finite equations use explicit Unity UV/world/sun/shadow/SH/final diffuse adapters; no complete native-lighting parity.
- v0.19 r3 passed162 rendered-player checks:23 bodies/9 Pokemon use authored Mid/Dark hues and92 Normal/AO/Spec/Rim bindings/56 linear texture contracts.900-frame mode1/2 A/B fixes source base/pose/light/camera/maps. Native bounded hue equations retain explicit scene/Cpre boundaries; masked Blinn/rim/final composition are adapters, not full native BRDF. Self-test input ignores focus and checks actual mixer/cooldown state.
