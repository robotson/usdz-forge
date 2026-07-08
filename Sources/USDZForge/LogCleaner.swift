import Foundation

/// Filters known-benign engine chatter out of the user-facing conversion log.
///
/// Two sources of harmless noise:
///  - USD's C++ packager emits a "_EnqueueDependency ... assetLocalization.cpp ...
///    Failed to resolve reference @0/texgen_0.jpg@" warning during an intermediate
///    localization pass. The texture IS embedded and resolves in the final USDZ
///    (verified) — the warning is cosmetic.
///  - The bundled Python's hashlib prints "unsupported hash type" on modern macOS
///    (OpenSSL legacy hashes absent); conversion is unaffected.
///
/// We hide these specific lines only — genuine errors pass through untouched.
enum LogCleaner {
    private static let noiseMarkers = [
        "assetLocalization.cpp",
        "_EnqueueDependency",
        "unsupported hash type",
        "code for hash",
    ]

    static func clean(_ log: String) -> String {
        log
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { line in !noiseMarkers.contains { line.contains($0) } }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
