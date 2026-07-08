# Morph targets / blendshapes (A2) — validation strategy & implementation notes

Status: **IMPLEMENTED (2026-07-08)** — `test_morph_conversion_matches_gltf_math`
passes on `AnimatedMorphCube` and the 8-target multi-primitive `MorphStressTest`;
Apple's `usdARKitChecker` passes the output. Remaining gaps: sparse target
accessors (dropped with a warning) and the on-device Quick Look playback check
(B6) — the in-app warning stays, softened to "authored, verify on device,"
until an iPhone confirms playback. The stress test also caught a real design
bug pre-ship: glTF targets are per-MESH, so multi-primitive meshes must bind
identical shape names per primitive, not append duplicates.

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

## Gold-standard findings (2026-07-08, all verified empirically)

**No converter oracle exists among our peers.** Apple's usdzconvert 0.62 has zero
morph code, and Google's usd_from_gltf — the purpose-built Quick Look converter —
has `// TODO: Morph targets.` + `UFG_WARN_MORPH_TARGETS_UNSUPPORTED`
(convert/converter.cc:613). Both industry GLB→USDZ tools warn-and-continue,
i.e. exactly our A1 behavior. Implementing A2 exceeds both.

**Blender 4.5 IS a working gold standard.** Headless
(`blender --background --python`) GLB→USD of AnimatedMorphCube authors:

```
SkelRoot                              <- synthesized (glTF has no skeleton!)
├─ Mesh [SkelBindingAPI, MaterialBindingAPI]
│   ├─ BlendShape "thin"   (24 offsets + explicit pointIndices)
│   └─ BlendShape "angle"        <- BlendShape prims are CHILDREN of the mesh
│   skel:blendShapes = [thin, angle]  + skel:blendShapeTargets rel
│   skel:skeleton -> ../Skel
└─ Skeleton "Skel" [SkelBindingAPI]   <- trivial, jointless host
    └─ SkelAnimation (blendShapes + per-frame baked blendShapeWeights)
```

This settles the morph-only-mesh question: synthesize a SkelRoot + jointless
Skeleton, put BlendShapes under the mesh, weights on a SkelAnimation bound via
the skeleton. (Also note Blender bakes weights per-frame; we can author the
sparse glTF keys directly.)

**The Tier-2 harness is validated against Blender.** Its math reproduces
Blender's deformed point clouds to **0.000000 worst error over 100 keyframes**,
after normalizing two things that differ in Blender's output but won't in ours:
vertex order (Blender permutes; Apple's engine reads accessors in order) and
stage up-axis (Blender exports Z-up; we author Y-up). Canonical
AnimatedMorphCube numbers: 24 verts, 2 targets (thin max |offset| 0.0189,
angle 0.0199), 127 weight keys over 4.20s, weights peak at 1.0.

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
