# Future scope — Reality Converter parity features (all demand-gated)

Decisions from 2026-07-08. Principle: converter-that-Just-Works, not
editor-that-competes-with-Apple. Nothing here gets built without a named user
who wants it.

## Material customization — ENGINE ALREADY SHIPS IT (UI gap only)

Reality Converter's "customize material properties with your own textures" was
a form over `usdzconvert` CLI flags, and those flags survived our port intact:

```
usdzconvert in.glb out.usdz \
  -m bodyMaterial -diffuseColor body.png -opacity a body.png \
  -metallic r orm.png -roughness g orm.png -normal normal.png -occlusion ao.png
```

Per-material scoping (`-m`), all PBR channels, texture-channel packing, constant
fallbacks. Power users can do this TODAY against the bundled engine. If demand
appears (e.g. mural texture swaps), the work is a per-material properties panel
in the app that assembles these args — a day, not an editor. `ConversionOptions`
in the Swift layer is the seam.

## IBL / lighting-environment preview — small viewer feature

Old Reality Converter previewed under selectable image-based lighting. Ours
would be: bundle 3–4 HDRIs, set `scene.lightingEnvironment.contents` in
`USDZPreviewView`, add a picker. ~1 hour. Useful for judging how a model reads
in AR before AirDropping. Build when someone asks to judge materials in-app.

## Full scene/material editor — SKIP, permanently

Reality Composer Pro owns this space (ships with Xcode — note that's a ~12 GB
install, so for non-dev users light material tweaks via the panel above may
still beat "install Xcode"). We stay a converter.
