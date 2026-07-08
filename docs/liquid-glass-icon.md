# Liquid Glass icon — research & upgrade plan

Research on adopting macOS 26 (Tahoe) "Liquid Glass" app icons for USDZ Forge.

## TL;DR

- Our current icon (`AppIcon.icns` via `CFBundleIconFile`) **renders fine on macOS 26** — Tahoe
  falls back to the legacy `.icns` cleanly. So Liquid Glass is a **polish upgrade, not a fix.**
- A Liquid Glass icon is a new **`.icon`** file authored in **Icon Composer** (ships with Xcode 26).
  It's a layered, material-based format the OS renders live (specular, refraction, translucency,
  shadow) across light / dark / tinted / clear appearances.
- Authoring is a **GUI task in Icon Composer** — there's no CLI to author one. But compiling it into
  our hand-assembled `.app` **is** scriptable via `actool`, so it fits our non-Xcode build.
- **Catch for us:** our current art is a *pre-rendered glossy 3D cube with baked lighting*. Liquid
  Glass wants **flat, un-lit layers** and applies its own material/lighting. So a proper adoption
  means re-authoring the cube as flat layers, not just importing the PNG we have.

## What Liquid Glass icons are

- Introduced at WWDC 2025 with the system-wide Liquid Glass redesign; authored in **Icon Composer**
  (ships with Xcode 26, runs on macOS Sequoia 15.3+).
- One **`.icon`** source file replaces the old pile of per-size PNGs / `.icns`, and the system
  renders every size/appearance from it.
- Per-layer materials in the Inspector: **Liquid Glass toggle, fill, opacity, blend mode, specular
  highlights, shadows (neutral or chromatic)**, plus per-appearance overrides for dark/tinted.

## Authoring constraints (from the field)

- **Max 4 layers** (performance/battery). Group by depth. Consolidate/merge to stay within it.
- **Canvas 1024px** (iPhone/iPad/Mac); watchOS is 1088px with a circular mask.
- Export each layer **individually**, **transparent background**, **no platform mask** (don't bake
  in the rounded-rect/circle). **SVG preferred** (crisp scaling); PNG allowed for textured/blur bits.
- **SVG gotcha:** design tools (Affinity, etc.) export stray `<rect>` backgrounds that break the
  glass effect — strip `<rect>` from the SVG, or use PNG.
- **Glass ✕ blur are mutually exclusive** per layer — pick one.
- **Monochrome/tinted** brightness is derived from your normal-mode colors; dark or saturated art can
  go muddy — assign explicit fills for the tinted variants.

## Build integration WITHOUT an Xcode project (our case)

We build via Swift Package + a hand-assembled `.app`. A `.icon` still compiles with `actool`
(part of the Xcode toolchain; **requires Xcode 26 + macOS 26 SDK on the build machine**):

```bash
# 1. Compile the .icon into an asset catalog (Assets.car) + a generated legacy .icns fallback.
xcrun actool AppIcon.icon \
  --compile "<out-dir>" \
  --app-icon AppIcon \
  --platform macosx --target-device mac \
  --minimum-deployment-target 26.0 \
  --include-all-app-icons \
  --enable-on-demand-resources NO \
  --development-region en \
  --output-partial-info-plist /dev/null

# 2. Copy Assets.car into the bundle
cp "<out-dir>/Assets.car" "USDZ Forge.app/Contents/Resources/Assets.car"
```

Info.plist keys:
- `CFBundleIconName` = `AppIcon`  ← Tahoe uses this (the Liquid Glass icon in `Assets.car`)
- Keep `CFBundleIconFile` = `AppIcon` and the legacy `AppIcon.icns` ← older macOS + some Finder paths

Backward compatibility: name the Icon Composer file **`AppIcon`**; macOS 26 uses the new one and
**older systems fall back to the legacy `.icns`**. Back-deployed Liquid Glass rendering is reported
**inconsistent** on older OSes — keeping the legacy `.icns` is the safe path (which we already do).

## Concrete plan for USDZ Forge (when we do it)

1. **Rebuild the art as flat layers** (not our baked-glossy render):
   - Layer A (background): the dark rounded-square fill — or omit and set a background color in
     Icon Composer's document settings (saves a layer).
   - Layer B (cube): a **flat, un-lit** isometric cube (three faces, solid amber/orange tones),
     exported as **SVG** with a transparent background and no rounded-rect.
   - Optional Layer C: the spark/glint.
   - Let Icon Composer add the glass material, specular, and shadow — don't bake them in.
2. In **Icon Composer**: import layers, enable Liquid Glass on the cube, tune specular/shadow, and
   check all six appearances (default, dark, clear light/dark, tinted light/dark). Save `AppIcon.icon`.
3. Add an `actool` step to `packaging/build-app.sh` (guarded so it's skipped when Xcode 26 isn't
   present), set `CFBundleIconName`, and keep the current `.icns` as the fallback.
4. Commit `packaging/AppIcon.icon` as the new source of truth (keep `icon-source.png` for reference).

**Effort:** ~1–2 hrs, mostly the Icon Composer GUI pass + re-drawing a flat cube. Needs Xcode 26 /
macOS 26 (this machine is on 26.5, so we're set). Best bundled with the notarization pass.

## Sources

- [Icon Composer — Apple Developer](https://developer.apple.com/icon-composer/)
- [Creating your app icon using Icon Composer — Apple Developer Documentation](https://developer.apple.com/documentation/Xcode/creating-your-app-icon-using-icon-composer)
- [Create icons with Icon Composer — WWDC25 session 361](https://developer.apple.com/videos/play/wwdc2025/361/)
- [Crafting Liquid Glass app icons with Icon Composer — Create with Swift](https://www.createwithswift.com/crafting-liquid-glass-app-icons-with-icon-composer/)
- [Icon Composer — Tackling Challenges (fatbobman)](https://fatbobman.com/en/posts/icon-composer-tackling-challenges/)
- [Supporting Liquid Glass Icons in Apps Without Xcode (Hendrik Erz)](https://www.hendrik-erz.de/post/supporting-liquid-glass-icons-in-apps-without-xcode)
- [Updating application icons for macOS 26 Tahoe and Liquid Glass (Successful Software)](https://successfulsoftware.net/2025/09/26/updating-application-icons-for-macos-26-tahoe-and-liquid-glass/)
- [actool(1) man page](https://keith.github.io/xcode-man-pages/actool.1.html)
- [Adding Icon Composer icons to Xcode (Use Your Loaf)](https://useyourloaf.com/blog/adding-icon-composer-icons-to-xcode/)
