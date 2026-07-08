import Foundation

/// Tier-1 updater: on launch (throttled to once a day) ask the GitHub Releases
/// API whether a newer version exists, and if so surface a banner that opens
/// the release page. Deliberately NOT an in-place auto-updater: replacing the
/// bundle safely (Sparkle) wants a notarized app and signed XPC helpers, so
/// that upgrade rides with the Developer ID / notarization pass.
enum UpdateChecker {
    struct Update: Equatable {
        let version: String
        let url: URL
    }

    private static let releasesLatest =
        URL(string: "https://api.github.com/repos/robotson/usdz-forge/releases/latest")!
    private static let lastCheckKey = "UpdateChecker.lastCheck"
    private static let checkInterval: TimeInterval = 60 * 60 * 24

    /// Returns a newer release if one exists. `nil` = up to date, unknown
    /// version (dev build), throttled, or offline — all silent no-ops.
    static func check(force: Bool = false) async -> Update? {
        guard let current = Bundle.main.object(
            forInfoDictionaryKey: "CFBundleShortVersionString") as? String else {
            return nil // `swift run` dev build: no Info.plist, skip
        }

        let defaults = UserDefaults.standard
        if !force {
            let last = defaults.double(forKey: lastCheckKey)
            guard Date().timeIntervalSince1970 - last > checkInterval else { return nil }
        }
        defaults.set(Date().timeIntervalSince1970, forKey: lastCheckKey)

        var request = URLRequest(url: releasesLatest)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let tag = json["tag_name"] as? String,
              let htmlURL = (json["html_url"] as? String).flatMap(URL.init(string:))
        else { return nil }

        let latest = tag.hasPrefix("v") ? String(tag.dropFirst()) : tag
        return isNewer(latest, than: current) ? Update(version: latest, url: htmlURL) : nil
    }

    /// Numeric dotted-version comparison ("0.1.2" > "0.1.1"); missing parts are 0.
    static func isNewer(_ candidate: String, than current: String) -> Bool {
        let a = candidate.split(separator: ".").map { Int($0) ?? 0 }
        let b = current.split(separator: ".").map { Int($0) ?? 0 }
        for i in 0..<max(a.count, b.count) {
            let x = i < a.count ? a[i] : 0
            let y = i < b.count ? b[i] : 0
            if x != y { return x > y }
        }
        return false
    }
}
