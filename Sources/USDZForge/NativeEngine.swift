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
            hasAnimation: USDZInspector.hasAnimation(at: output)
        )
    }
}
