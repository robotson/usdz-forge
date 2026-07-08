# Morph targets / blendshapes (A2) — validation strategy & implementation notes

Status: **not implemented** (inputs warn loudly; see `docs/correctness-plan.md` A1).
This doc exists so the implementation lands against a *pre-built* acceptance
harness instead of "convert it and eyeball the preview."

## How we'll know it's correct — three tiers

**Tier 1 — structure** (`tests/test_conversion.py`): BlendShape prims exist,
`blendShapeWeights` has >1 time samples, counts match the glTF ground truth.
`anim_probe.py` already reports these fields.

**Tier 2 — semantics, the gold standard** (`tests/test_morph_semantics.py`,
ALREADY WRITTEN, auto-skips until A2 lands): glTF defines morphing exactly as
`deformed(t) = base + Σ wᵢ(t)·targetᵢ`. The test computes expected vertex
positions **independently from the raw GLB bytes** (own tiny GLB parser, no
engine code shared), reads what we authored into USD (base points + BlendShape
offsets + weight curve), and asserts the deformed positions match per-vertex
per-keyframe within 1e-4. Conversion semantics proven without any renderer.
Fixtures: `AnimatedMorphCube`, `AnimatedMorphSphere` (both non-sparse).

**Tier 3 — compatibility**: Apple's bundled `usdARKitChecker` must stay green
(now asserted per-fixture in CI), and the **manual on-device Quick Look check
remains the final word** — blendshape *playback* in AR Quick Look is
historically unreliable, so even a semantically perfect file may not animate
on-device. Until on-device playback is confirmed, the in-app morph warning
stays (softened to "authored but may not play in Quick Look").

## Implementation sketch (usdStageWithGlTF.py)

1. **Parse:** mesh `primitives[].targets` (POSITION/NORMAL displacement
   accessors; handle sparse accessors) + animation channels with
   `target.path == "weights"`.
2. **Author:** `UsdSkel.BlendShape` prims (offsets = target displacements) under
   the mesh; on the mesh's `UsdSkel.BindingAPI` (Apply it!): `skel:blendShapes`
   token order + `skel:blendShapeTargets` rel.
3. **Animate:** time-sampled `blendShapeWeights` on the `SkelAnimation`, order
   matching the anim's `blendShapes` attr.
4. **The structural catch:** UsdSkel blendshapes only evaluate under a
   `SkelRoot` with a bound `Skeleton`. glTF morph meshes often have NO skin —
   so a morph-only mesh needs a synthetic SkelRoot + trivial one-joint Skeleton
   wrapper. This is the fiddly part; CesiumMan-style skinned+morphed meshes
   reuse their existing skeleton instead.
5. Remove/soften the A1 warning per Tier 3 above.

## Definition of done

- `test_morph_conversion_matches_gltf_math` un-skips and passes (both fixtures)
- Tier 1 counts asserted; `usdARKitChecker` still green on all fixtures
- On-device Quick Look playback tested and the result documented honestly
  (plays / authored-but-static), warning text updated to match reality
