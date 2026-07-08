# USDZ Forge — Stress-Test Asset Battery + Priority Fixes

External review doc, grounded in live conversions against v0.2.0 on OpenUSD 26.5.
STATUS (2026-07-08): BUG-1 and BUG-2 below are FIXED; the battery's CI-able tiers
are implemented in tests/test_conversion.py (34 tests green).

## Testing philosophy — three layers, don't conflate them

1. **Data-level (CI-automatable).** Open the output `.usdz` and assert on its *content*
   — animation time samples, blendshape weights, embedded textures, mesh point counts,
   package integrity. Catches the "converts successfully but is frozen/empty" bug class.
   Exit code 0 is necessary, never sufficient.
2. **On-device (manual, NOT automatable).** AR Quick Look rendering on a real iPhone.
   USD-level correctness does not prove Quick Look *plays* it (esp. blendshapes). This is
   a checklist, not a CI job. See docs/on-device-checklist.md.
3. **Real-world robustness (the layer the clean Khronos toys miss).** Draco compression,
   sparse accessors, multi-material, KHR material extensions, package size. Production
   exports are messy in ways the sample animation assets are not. **This is where both
   crashes below were found.**

## Confirmed findings from live runs

| # | Input | Result on v0.2.0 | Resolution |
|---|---|---|---|
| **BUG-1** | **Draco-compressed GLB** (`KHR_draco_mesh_compression`) | CRASH — `KeyError: 'bufferView'` (Draco geometry lives in the extension, not plain accessors) | **FIXED**: detected at stage-build; fails with actionable guidance (re-export or `npx @gltf-transform/cli copy in.glb out.glb`). Vendored fixture `tests/vendored/BoxAnimated_draco.glb` + `test_draco_rejected_cleanly`. Full decode = future work, demand-gated. |
| **BUG-2** | **RecursiveSkeletons** (strided/interleaved accessors) | CRASH — `TypeError: can only concatenate str (not "bytes")` | **FIXED**: `data = ''` → `data = b''` in `Accessor` (Py2 relic; broke ALL strided bufferViews, not just this model). Regression test asserts 84 meshes / 4 skeletons / animated. |
| OK | BoxAnimated, CesiumMan, BrainStem, RiggedFigure, RiggedSimple | node + skeletal animation correct | asserted in CI |
| OK | Fox | all 3 clips authored | asserted in CI |
| OK | AnimatedMorphCube, MorphStressTest | blendshapes authored, math-validated, on-device verified | asserted in CI |
| OK | MorphPrimitivesTest | **sparse** morph accessors → targets dropped WITH warning (never silent) | asserted in CI |
| OK | Lantern, DamagedHelmet, MaterialsVariantsShoe, DragonAttenuation | heavy PBR / KHR extensions convert without crash; Lantern size flagged under 20 MB cap | asserted in CI |
| OK | InterpolationTest | STEP/LINEAR/CUBICSPLINE all animate | asserted in CI |
| OK | up-axis | outputs authored Y-up (the original "orientation whacked in Preview" complaint) | asserted in CI |

## Gaps that remain (all demand-gated)

- **Sparse morph accessors:** dropped with a warning today. Blender/Maya exports often
  write sparse morphs — implement decode when a real asset needs it (the warning makes
  the need visible).
- **Draco decode:** clean rejection today. If Catherine's pipeline emits Draco, add a
  decoder; check a real file's `extensionsUsed` first.
- **Skinned + morph on one mesh:** no public Khronos fixture exists; the classic real-
  character composite. Needs one of Catherine's real rigs or a generated asset — the
  most valuable missing device test for the murals use case.

## On-device checklist additions

Tracked in docs/on-device-checklist.md: MorphStressTest simultaneous-blend, skin+morph
composite (when an asset exists), orientation spot-check on a directional asset, and
batch-output equivalence (batch .usdz opens identically to single-file output).
