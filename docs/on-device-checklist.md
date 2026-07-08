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

- MorphStressTest (8 targets) on-device — do simultaneous morph targets actually blend?
- Fox (multi-clip) — confirm which clip Quick Look plays
- **Skinned + morph on one mesh** — the classic real-character composite; needs a real
  rig (no public fixture exists). Highest-value device test for the murals work.
- Orientation spot-check on a directional asset (Fox/CesiumMan) — no flips in AR
  (CI asserts Y-up metadata; eyes confirm the look)
- Batch outputs — a folder run through batch opens identically to single-file conversions
- A large real-world production model (murals pipeline)
