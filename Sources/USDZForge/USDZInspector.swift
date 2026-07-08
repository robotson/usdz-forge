import Foundation

/// Lightweight, dependency-free check for whether a produced USDZ actually
/// carries animation. A USDZ is an uncompressed zip; the crosswire we look for
/// (`timeSamples`) appears as plain bytes in the packaged `.usdc`, so a raw
/// byte scan is enough to answer "did the animation survive?" without linking
/// USD. Good enough to flag the single-animation-timeline gotcha in the UI.
enum USDZInspector {
    static func hasAnimation(at url: URL) -> Bool? {
        guard let data = try? Data(contentsOf: url, options: .mappedIfSafe) else {
            return nil
        }
        return data.range(of: Data("timeSamples".utf8)) != nil
    }
}
