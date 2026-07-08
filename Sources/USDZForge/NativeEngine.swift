import Foundation

/// Phase 2 engine: Apple's `usdzconvert` pipeline (the exact Reality Converter
/// logic) ported to Python 3 and run against a modern **arm64** OpenUSD 26.5
/// (`usd-core`). No Rosetta, no dead XPC, no Python 2.7.
///
/// Validated: output is structurally identical to the Phase-1 oracle (the
/// original engine) on both BoxAnimated (node animation) and CesiumMan (skinned
/// skeletal animation + embedded texture). This is the distribution-grade engine.
struct NativeEngine: ConversionEngine {
    let displayName = "Native arm64 · OpenUSD 26 (faithful)"
    let pythonURL: URL
    let scriptURL: URL

    /// - Parameter engineRoot: the `usdz-forge/engine` directory (dev), or the
    ///   bundled engine dir inside the .app (distribution).
    init(engineRoot: URL) {
        self.pythonURL = engineRoot
            .appendingPathComponent("python/bin/python3.14")
        self.scriptURL = engineRoot
            .appendingPathComponent("native/usdzconvert")
    }

    var isAvailable: Bool {
        let fm = FileManager.default
        return fm.isExecutableFile(atPath: pythonURL.path)
            && fm.fileExists(atPath: scriptURL.path)
    }

    func convert(input: URL, output: URL, options: ConversionOptions) throws -> ConversionResult {
        guard isAvailable else {
            throw ConversionError.engineUnavailable(scriptURL.path)
        }

        let process = Process()
        process.executableURL = pythonURL
        var args = [scriptURL.path]
        if options.verbose { args.append("-v") }
        args.append(input.path)
        args.append(output.path)
        process.arguments = args

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        let log = String(data: data, encoding: .utf8) ?? ""
        guard process.terminationStatus == 0,
              FileManager.default.fileExists(atPath: output.path) else {
            throw ConversionError.conversionFailed(log)
        }

        return ConversionResult(
            outputURL: output,
            log: LogCleaner.clean(log),
            hasAnimation: probeAnimation(output)
        )
    }

    /// Ask USD (via the bundled interpreter) whether the output actually carries
    /// animation. Reliable for skeletal/UsdSkel animation in binary crate files,
    /// where a raw byte scan for "timeSamples" gives false negatives.
    private func probeAnimation(_ usdz: URL) -> Bool? {
        let probe = scriptURL.deletingLastPathComponent()
            .appendingPathComponent("probe_usdz.py")
        guard FileManager.default.fileExists(atPath: probe.path) else { return nil }

        let process = Process()
        process.executableURL = pythonURL
        process.arguments = [probe.path, usdz.path]
        let out = Pipe()
        process.standardOutput = out
        process.standardError = Pipe() // discard interpreter noise
        do { try process.run() } catch { return nil }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        switch String(data: data, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) {
        case "1": return true
        case "0": return false
        default:  return nil
        }
    }
}
