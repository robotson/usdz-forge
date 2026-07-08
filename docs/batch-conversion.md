# Batch conversion — spec & decisions

Motivated by a real workload (many mural models to convert). Spec informed by an
external review; decisions recorded here so the constraints survive refactors.

## The non-negotiable principle

**One bad file must not sink the run.** The point of batch is walking away from
it. Every conversion is isolated (`do/catch` per item), failures are recorded,
and the batch always finishes and reports the truth.

## Behavior (implemented)

- **Input:** multi-file drop and folder drop. Folders are scanned
  **recursively** (hidden files and package contents skipped) for
  `.glb`/`.gltf`/`.obj`. Outputs are written next to inputs, so a converted
  tree mirrors itself.
- **Isolation:** per-file convert in a sequential background loop; a failure is
  caught, recorded on that row, and the batch continues.
- **Truthful summary:** `Converted N/M · X failed · Y skipped · Z morph warnings`.
  Per-row status: pending / converting / ✅ done / ⚠️ done-with-morph-warning /
  ❌ failed / ⏭ skipped / 🛑 cancelled — because in a 40-file batch, a warning
  that only appears in a scrolling log is a warning nobody saw.
- **Per-file animation truth:** each result carries the USD-level animation
  probe (film icon = animation actually present in the output) and the morph
  warning — reusing the same probe philosophy as the test suite.
- **Collision policy:** default is **skip existing** `.usdz` outputs (ideal for
  re-running a folder pipeline); an "Overwrite existing" checkbox flips it.
- **Cancel:** Stop button sets a token; the in-flight file finishes cleanly,
  remaining items are marked cancelled. No corrupted outputs, summary stays true.
- **Inspection:** click any row to load its output in the 3D preview + its log.

## Deliberately NOT built (scope guard)

- No worker-pool concurrency (sequential is fine for this scale; revisit only
  if real batches feel slow).
- No queue persistence, pause/resume, or retry system — this is a tool for a
  handful of users, not a render farm.

## Engine-level guarantee (tested)

`tests/test_conversion.py::test_corrupt_input_fails_cleanly` asserts a garbage
input exits nonzero **without producing an output file** — the contract the
batch loop's failure containment depends on.
