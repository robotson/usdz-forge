# Vendored Draco decoder

Google Draco v1.5.7, Apache-2.0. The full upstream licence is in `LICENSE`.
These are Google's versioned, prebuilt decoder files; no Draco compiler or
runtime download is required by the app.

- `draco_wasm_wrapper.js`: https://www.gstatic.com/draco/versioned/decoders/1.5.7/draco_wasm_wrapper.js
  (SHA-256 `e8049906ef3f8f75d3456c22a3f31bfdfe5b5b5bd09ccdec613b9e9a49d554d8`)
- `draco_decoder.wasm`: https://www.gstatic.com/draco/versioned/decoders/1.5.7/draco_decoder.wasm
  (SHA-256 `2516a4e43526d71787bf2f678f951329f7f858f8f15f42d4bc9e370b31a0da3a`)

The Python bridge loads these locally in the macOS JavaScriptCore framework.
`packaging/build-app.sh` copies the entire `engine/native` tree into the app.
