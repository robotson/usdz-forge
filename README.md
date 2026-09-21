# USDZ Forge

[![tests](https://github.com/robotson/usdz-forge/actions/workflows/tests.yml/badge.svg)](https://github.com/robotson/usdz-forge/actions/workflows/tests.yml)

A small, native macOS app that converts **GLB / glTF / OBJ → animated USDZ** by drag-and-drop,
with a live 3D preview. It's a modern, self-contained successor to Apple's discontinued
**Reality Converter**.

<img alt="USDZ Forge" src="docs/screenshot.png" width="480">

## Why

Apple's Reality Converter was removed after WWDC 25 and no longer runs on current macOS —
its conversion helper hard-links **system Python 2.7**, which Apple removed in macOS 12.3.
The underlying engine (Apple's `usdzconvert`), however, is solid and MIT-licensed.

USDZ Forge takes that exact engine, ports it to **Python 3 + modern OpenUSD (26.x)**, and wraps it
in a native SwiftUI app. The Python interpreter, OpenUSD, and the converter are all **bundled inside
the app** — nothing needs to be installed on the target machine.

## Features

- Drag-and-drop GLB / glTF / OBJ → USDZ, single files or whole folders (batch)
- **Animation preserved** — node transforms, skeletal/skinned (UsdSkel), and
  morph targets/blendshapes (authored as `UsdSkel.BlendShape`; validated
  per-vertex against the glTF spec math)
- PBR materials + textures embedded into the package
- Draco-compressed GLB input (`KHR_draco_mesh_compression`) decoded locally,
  preserving skeletal animation and morph targets without Node or a compiler
- Live in-window 3D preview with animation playback (SceneKit)
- Flags in the UI whether the output actually carries animation
- Fully self-contained, **Apple-Silicon native (no Rosetta)**

## Requirements

- macOS 13 (Ventura) or later
- Apple Silicon (M1 or newer) for conversion. On Intel Macs the app launches
  and explains the limitation (the bundled engine is arm64-only).

## Install (prebuilt)

Download the latest `USDZ-Forge.zip` from Releases, unzip, and move `USDZ Forge.app` to
`/Applications`. Because the app is ad-hoc signed, the first launch needs **right-click → Open**
(a one-time Gatekeeper step for un-notarized apps).

## Build from source

Prerequisites: Xcode 15+ (Swift 5.9+), `curl`, and an internet connection for the one-time
engine bootstrap.

```bash
# 1. Bootstrap the bundled engine: downloads a relocatable CPython + installs OpenUSD (usd-core)
./engine/setup-engine.sh

# 2. Build the Swift app
swift build -c release

# 3. Assemble + sign the self-contained .app and emit dist/USDZ-Forge.zip
./packaging/build-app.sh
```

The app resolves its engine from `Contents/Resources/engine` when bundled. For `swift run`
during development, point it at the source engine with:

```bash
USDZFORGE_ENGINE_ROOT="$PWD/engine" swift run
```

## Notes & limitations

- **USDZ / AR Quick Look plays a single animation timeline.** Source files with multiple
  animation clips will keep only one. This is a USDZ format constraint, not a tool bug.
- **Morph targets / blendshapes are supported**, including sparse target accessors — a capability both Apple's original
  converter and Google's usd_from_gltf lack (they drop morphs entirely). Output is
  validated per-vertex against the glTF spec math and Apple's ARKit validator, and
  **playback is verified on-device in AR Quick Look**, including Draco-decoded
  skinning and a sparse-accessor blend shape (21 Sep 2026: a rigged coyote and a
  morph-target eagle, both converted from Draco input, played correctly on device).
- **Draco is decoded for `.glb` only.** A plain `.gltf` (separate `.bin`) using
  `KHR_draco_mesh_compression` still fails with the actionable re-export message.
- **TODO — warn when a rig's rest pose disagrees with its animation.** Many vendor
  models carry a default joint pose 90° (or a whole unit scale) away from what their
  own clip sets at frame 0. glTF viewers autoplay, so nobody sees it; USD keeps that
  default as the skeleton's rest pose, and any viewer that does *not* play the clip —
  Xcode's preview, Finder thumbnails, an engine importing without playback — draws the
  model nose-down, tiny, or underground. Found in the wild: nine of nine rigged animals
  in a museum delivery, reported by the client after release. The converter is behaving
  correctly by carrying the source across faithfully, so the fix is to **tell the truth
  about it**, in the same spirit as the existing animation probe: flag the disagreement
  after conversion, and offer an opt-in re-base of the rest pose onto frame 0 (exact for
  linear blend skinning: transform points and bind matrices by the same matrix, and the
  animated result is unchanged).
- Ad-hoc signed builds show a Gatekeeper prompt on first open. For frictionless distribution,
  re-sign with an Apple **Developer ID** identity and notarize (`notarytool` + `stapler`).

## Credits & license

- App code: MIT (see [LICENSE](LICENSE)).
- Conversion engine: Apple's `usdzconvert` (© Apple Inc., MIT) — ported to Python 3 / modern
  OpenUSD. Apple's original notice is retained in `engine/native/LICENSE.txt`.
- Draco decoder: Google Draco v1.5.7 (Apache-2.0), vendored with its license and
  provenance in `engine/native/vendor/draco/`.
- [OpenUSD](https://openusd.org) via the `usd-core` wheel.
- Relocatable interpreter via [python-build-standalone](https://github.com/astral-sh/python-build-standalone).
