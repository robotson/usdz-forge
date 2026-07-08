# On-device verification checklist (B6)

USD-level tests prove the *data* is correct; only a device proves Apple's
renderers *play* it. Record results here per release / iOS version.

## How to run a check

1. Convert the fixture (`tests/fixtures/*.glb`) with the app or CLI.
2. AirDrop the `.usdz` to an iPhone/iPad, tap to open in AR Quick Look.
3. Confirm the model appears, is textured, and animates as expected — in both
   object mode and AR (in-room) mode.

## Results

| Date | Fixture | Animation type | Device context | Result |
|---|---|---|---|---|
| 2026-07-08 | CesiumMan | skeletal/skinned | iPhone, AR Quick Look | ✅ plays, textured |
| 2026-07-08 | AnimatedMorphCube | **morph/blendshape** | iPhone, AR Quick Look (in-room AR) | ✅ **plays** — synthesized-SkelRoot blendshape structure confirmed working on-device |
| 2026-07-08 | RobotExpressive (armature scale=100) | rigid + skinned | iPhone, AR Quick Look | ✅ after v0.2.2+v0.2.3 bind-space fixes (was: blank, then disembodied hands — both were engine bugs, both fixed + regression-tested) |
| 2026-07-08 | RobotExpressive-morphtest (injected weights) | **skeletal + blendshape SIMULTANEOUSLY** | macOS Quick Look (RealityKit) | ✅ **both play together** — clip animates while eyebrows/eyes visibly pulse the Surprised morph. iPhone spot-check still worth logging. |

## Still to spot-check when convenient

- MorphStressTest (8 targets) on-device — do simultaneous morph targets actually blend?
- Fox (multi-clip) — confirm which clip Quick Look plays
- **Skinned + morph playing TOGETHER** — ✅ answered on macOS Quick Look (see table);
  re-log on iPhone when convenient. **Methodology footnote:** the raw three.js clips
  carry morph-weight channels that are FLAT ZERO (three.js drives expressions from GUI
  sliders, not clips) — testing with the unmodified asset shows no morphs and would
  wrongly read as failure. Use an injected-weights variant (pulse one shape at ~1 Hz;
  see the `inject_morph.py` approach in the session notes / flatten stage → set
  blendShapeWeights samples → `UsdUtils.CreateNewARKitUsdzPackage`).
- Orientation spot-check on a directional asset (Fox/CesiumMan) — no flips in AR
  (CI asserts Y-up metadata; eyes confirm the look)
- Batch outputs — a folder run through batch opens identically to single-file conversions
- A large real-world production model (murals pipeline)
