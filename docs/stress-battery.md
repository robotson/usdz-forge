# USDZ Forge — Stress-Test Asset Battery + Priority Fixes

External review doc, grounded in live conversions against v0.2.0 on OpenUSD 26.5.
STATUS (2026-07-08): BUG-1 and BUG-2 below are FIXED; the battery's CI-able tiers
are implemented in tests/test_conversion.py (34 tests green).
UPDATE (2026-09-16): real CCA demand triggered Draco decoding. A pinned Google
WebAssembly decoder now runs through macOS JavaScriptCore and rewrites compressed
GLBs into plain temporary GLBs before the existing USD reader. Sparse morph
accessors are also expanded. See the current-state notes below; the v0.2.0
findings remain here as historical evidence.

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
| **BUG-1** | **Draco-compressed GLB** (`KHR_draco_mesh_compression`) | CRASH — `KeyError: 'bufferView'` (Draco geometry lives in the extension, not plain accessors) | **FIXED**: compressed GLBs now decode before stage-build. `test_draco_converts_and_keeps_animation` and an optional rigged CCA twin test cover output; unavailable decoder still gives actionable guidance. |
| **BUG-2** | **RecursiveSkeletons** (strided/interleaved accessors) | CRASH — `TypeError: can only concatenate str (not "bytes")` | **FIXED**: `data = ''` → `data = b''` in `Accessor` (Py2 relic; broke ALL strided bufferViews, not just this model). Regression test asserts 84 meshes / 4 skeletons / animated. |
| OK | BoxAnimated, CesiumMan, BrainStem, RiggedFigure, RiggedSimple | node + skeletal animation correct | asserted in CI |
| OK | Fox | all 3 clips authored | asserted in CI |
| OK | AnimatedMorphCube, MorphStressTest | blendshapes authored, math-validated, on-device verified | asserted in CI |
| OK | MorphPrimitivesTest | originally sparse morph accessors were dropped with a warning | sparse accessors now expanded; CI checks authoring |
| OK | Lantern, DamagedHelmet, MaterialsVariantsShoe, DragonAttenuation | heavy PBR / KHR extensions convert without crash; Lantern size flagged under 20 MB cap | asserted in CI |
| OK | InterpolationTest | STEP/LINEAR/CUBICSPLINE all animate | asserted in CI |
| OK | up-axis | outputs authored Y-up (the original "orientation whacked in Preview" complaint) | asserted in CI |

## Current Draco evidence and remaining checks

- The vendored `BoxAnimated_draco.glb` converts and retains node animation;
  simulated decoder unavailability keeps the clean rejection message.
- Local compressed/uncompressed CCA bobcat and eagle twin tests pass. For the
  skinned bobcat, baked point clouds at frames 0, midpoint, and 249 differ by
  at most about 0.000102 m (Draco can reorder/split vertices); the test bounds
  this at 0.0002 m in both directions. Eagle retains a sparse morph target and
  27 blend-weight samples; its weight-1 deformed point cloud matches its twin.
  The client GLBs are not vendored; pass their paths through the two environment
  variables documented in `tests/test_draco_cca_pair.py` to repeat this test.
- Largest CCA Draco geometry payload checked: black oak, 4,364,894 compressed
  bytes; decode plus GLB rewrite took 5.5 seconds on this machine. Full USDZ
  conversion succeeded. The package contains its textures, despite an existing
  OpenUSD asset-localization warning also present for the uncompressed twin.
- All 31 top-level CCA delivery GLBs converted in a 142-second sweep with no
  failures; all resulting USDZs opened as USD stages and passed ZIP integrity.
- A new on-device AR Quick Look check is still needed for Draco + sparse-morph
  playback. Data-level success alone cannot establish device playback.

## On-device checklist additions

Tracked in docs/on-device-checklist.md: MorphStressTest simultaneous-blend, skin+morph
composite (when an asset exists), orientation spot-check on a directional asset, and
batch-output equivalence (batch .usdz opens identically to single-file output).
