# USDZ Forge — Fix conversion correctness + add regression testing

## Context

USDZ Forge converts GLB/glTF → USDZ by wrapping a Python-3 port of Apple's `usdzconvert` (in `engine/native/`, driven by `usdStageWithGlTF.py`) inside a SwiftUI app. It bundles CPython + OpenUSD (`usd-core`, 26.x).

An external review ran the engine against Khronos sample assets on OpenUSD 26.5 and found: **rigid and skeletal/skinned animation are preserved correctly, but morph/blendshape animation is silently dropped, and the docs claim morph support that does not exist.** The dangerous failure mode is that a morph-animated file converts with exit code 0 and no error, producing a frozen model. Your job is to (A) make the tool's behavior and its documentation honest and correct, and (B) build automated tests whose whole purpose is to catch "converts successfully but produces static/wrong output" — because that bug class passes any exit-code or file-exists check.

## Verified ground-truth baseline (encode these as test expectations)

Converted on OpenUSD 26.5 via `engine/native/usdzconvert <in>.glb <out>.usdz`:

| Asset | Type | Result today | Output facts to assert |
|---|---|---|---|
| `BoxAnimated` | rigid/node | ✅ animated | Xformable ops with time samples: `translate` ≈4 samples, `orient` ≈2 samples; stage range ≈0–89 |
| `CesiumMan` | skinned | ✅ animated | one `UsdSkel.Animation`; 19 joints; rotations AND translations each ≈48 time samples; range ≈1–48; `texgen_0.jpg` embedded in the `.usdz` zip |
| `AnimatedMorphCube` | morph | ❌ **static (bug)** | today: stage range `0..0`, no animation. Engine has **no** morph-target code — only `WEIGHTS_0` (skin joint weights) is read; glTF morph `targets`/`weights` are never processed |

## Part A — Conversion & documentation fixes

Priority order. A1–A3 are required for the next release; A4–A6 are follow-ups.

**A1. Stop the silent morph failure.** When input glTF contains morph targets and/or morph-target animation, the tool must not pretend success. Detect morph targets during conversion and either (a) implement them (see A2) or, until then, (b) emit a clear warning to stderr AND surface it in the app UI ("Morph/blendshape animation detected — not supported, output will be static for those meshes"). Never let morph input produce a silently static file with no signal.

**A2. (Stretch) Implement morph → USdSkel BlendShapes.** Read glTF mesh `targets` + animation channels targeting `weights`, author `UsdSkel.BlendShape` prims and time-sampled blendshape weight animation. IMPORTANT: even if authored correctly, iOS AR Quick Look historically does not play blendshape animation reliably — so this must be verified on-device before any doc claims it works. If on-device playback fails, keep the data but document it as "authored but not played by Quick Look," and keep the A1 warning.

**A3. Make the docs true.** `README.md` currently contradicts itself: the Features list claims "morph targets" preserved while Notes admits "morph-only animation may not survive." Fix both README and the GitHub release notes to state the verified reality: node + skeletal/skinned animation preserved; morph/blendshape not supported (or "experimental, not played by Quick Look" if A2 lands). Keep the accurate single-animation-timeline note.

**A4. Universal binary for Intel.** The app is currently Apple-Silicon-only, which breaks it on Intel Macs (including the machines this tool was originally meant to serve). `usd-core` ships x86_64 macOS wheels, so investigate a `universal2` (arm64 + x86_64) engine + app build. If arm64-only remains, the app must detect Intel at launch and show a clear, specific message instead of failing opaquely.

**A5. Notarization path.** Document (and script where possible) Developer ID signing + `notarytool` + `stapler` so distribution doesn't depend on the right-click-Open workaround and survives quarantine flags on downloaded zips.

**A6. Clean up the benign texture-localization warning** (`Failed to resolve reference @0/texgen_0.jpg@`) that appears even when the texture does embed correctly, so real problems aren't lost in noise.

## Part B — Automated regression testing

Design goal: **assert on the semantic animation content of the output USD, not on exit codes or file existence.** The original T-pose class of bug produces a valid file with a zero exit code; only inspecting the output for time-sampled animation catches it.

**B1. Fixture matrix.** Vendor (or fetch + cache) a small set of Khronos glTF-Sample-Assets covering every path, each with a declared "expected animation profile":
- Rigid/node: `BoxAnimated`
- Skinned: `CesiumMan`, plus `BrainStem` and/or `RiggedFigure` for a second/third rig
- Morph: `AnimatedMorphCube`, `AnimatedMorphSphere`
- Multi-clip: `Fox` (3 clips) — used to assert the documented single-timeline behavior, not treated as a failure
- Textured PBR: e.g. `DamagedHelmet` (texture-embedding assertion)
- Static control: plain `Box` (assert NO spurious animation is invented)

**B2. Output-inspection library.** Factor the review's probe into a reusable module (`tests/anim_probe.py`) that opens a `.usdz` and returns a structured profile:
- per-`UsdSkel.Animation`: joint count, and time-sample counts for rotations/translations/scales
- per-Xformable: xform-op time-sample counts
- blendshape presence + weight time samples
- stage start/end timeCode
- embedded file list from the `.usdz` zip (for texture assertions)

Proven starting point (works on OpenUSD 26.5; note the filename must NOT be `inspect.py` — it shadows the stdlib module pxr imports):

```python
from pxr import Usd, UsdSkel, UsdGeom

def profile(path):
    stage = Usd.Stage.Open(path)
    out = {"range": (stage.GetStartTimeCode(), stage.GetEndTimeCode()),
           "skel_anims": [], "xform_anim_ops": 0, "blendshapes": []}
    for prim in stage.Traverse():
        if prim.GetTypeName() == "SkelAnimation":
            a = UsdSkel.Animation(prim)
            out["skel_anims"].append({
                "joints": len(a.GetJointsAttr().Get() or []),
                "rot_samples": len(a.GetRotationsAttr().GetTimeSamples()),
                "trans_samples": len(a.GetTranslationsAttr().GetTimeSamples()),
            })
        if prim.IsA(UsdGeom.Xformable):
            for op in UsdGeom.Xformable(prim).GetOrderedXformOps():
                if len(op.GetTimeSamples()) > 1:
                    out["xform_anim_ops"] += 1
    return out
```

**B3. Parametrized pytest suite.** One test per fixture, asserting its profile against the declared expectation, e.g.:
- `CesiumMan`: exactly 1 skel anim, joints ≥ 19, rot_samples > 1 and trans_samples > 1, range spans multiple frames → **guards the T-pose regression**
- `BoxAnimated`: xform_anim_ops > 0
- `AnimatedMorphCube`: asserts the *documented* behavior — either blendshape weight animation present (if A2 lands) OR the conversion emitted the A1 morph warning. Never asserts silent static success.
- `DamagedHelmet`: expected texture files present in the `.usdz` zip
- static `Box`: zero animation of any kind

**B4. Validation + package integrity checks (every fixture).** Run the bundled `engine/native/usdARKitChecker` on each output and assert it passes. Assert each `.usdz` is a valid zip whose first entry is the `.usdc`, with no absolute/`../` paths.

**B5. CI.** GitHub Actions on a macOS arm64 runner: install the engine deps, run pytest, block releases on failure. If A4 lands, add an x86_64 leg. Make the suite a required pre-release gate (`make test` or equivalent).

**B6. On-device verification is separate and manual.** USD-level animation presence proves the *data* is correct; it does NOT prove AR Quick Look *renders* it (Quick Look has its own limits — single timeline, shaky/no morph playback). Add `docs/on-device-checklist.md`: convert each fixture, AirDrop to an iPhone, tap in Quick Look, confirm each animates as expected, and record pass/fail per iOS version. Treat this as the release sign-off that CI cannot cover.

## Acceptance criteria

- [ ] Morph input never produces a silently static file — it either animates (A2) or warns loudly in CLI + UI (A1).
- [ ] README and release notes match verified behavior; the Features/Notes contradiction is gone.
- [ ] `tests/anim_probe.py` + parametrized pytest suite exists and passes, with a `CesiumMan` skinned-animation assertion that would fail if skeletal animation were dropped.
- [ ] `usdARKitChecker` runs green on every fixture output.
- [ ] CI runs the suite and gates releases.
- [ ] `docs/on-device-checklist.md` exists.
- [ ] Intel behavior resolved (universal build) or a clear launch-time message on unsupported hardware.

## Working notes
- The engine entry point is `engine/native/usdzconvert <in> <out> [-v]`; `PYTHONPATH` must include `engine/native`.
- The animation-baking logic lives in `usdStageWithGlTF.py` (`processSkeletonAnimation`, `prepareSkinning`, `processPrimitive`). Morph work belongs alongside these.
- Do not name any test file `inspect.py` — it shadows a stdlib module that `pxr` imports and breaks the whole suite.
