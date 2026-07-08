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

## Still to spot-check when convenient

- MorphStressTest (8 targets) on-device — heavier blendshape load
- Fox (multi-clip) — confirm which clip Quick Look plays
- A large real-world production model (murals pipeline)
