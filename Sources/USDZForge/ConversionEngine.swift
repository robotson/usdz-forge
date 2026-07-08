import Foundation

/// Options that map onto the underlying converter flags.
/// Kept intentionally small for Phase 1; grows as we expose more of the
/// original Reality Converter feature set (iOS12 compat, metersPerUnit, etc.).
struct ConversionOptions {
    var verbose: Bool = true
}

struct ConversionResult {
    let outputURL: URL
    let log: String
    /// Whether the produced USDZ carries animation timeSamples. `nil` if not inspected.
    let hasAnimation: Bool?
    /// True when the source contained morph targets/blendshapes, which this
    /// engine does not support — the output will be static for those meshes.
    var morphWarning: Bool = false
}

enum ConversionError: LocalizedError {
    case engineUnavailable(String)
    case conversionFailed(String)

    var errorDescription: String? {
        switch self {
        case .engineUnavailable(let path):
            return "Converter engine not found at:\n\(path)"
        case .conversionFailed(let log):
            return "Conversion failed.\n\n\(log)"
        }
    }
}

/// The seam that lets us swap the Phase 1 (faithful Apple/Python) engine for a
/// Phase 2 (native arm64) engine without touching the UI. The GUI only ever
/// talks to this protocol.
protocol ConversionEngine {
    /// Human-readable name shown in the UI.
    var displayName: String { get }
    /// Whether the engine's backing executable is present and runnable.
    var isAvailable: Bool { get }
    /// Convert `input` (.glb/.gltf/.obj/…) to a USDZ at `output`.
    func convert(input: URL, output: URL, options: ConversionOptions) throws -> ConversionResult
}
