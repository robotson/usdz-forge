// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "USDZForge",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "USDZForge",
            path: "Sources/USDZForge"
        )
    ],
    // Language mode 5 keeps the drag-and-drop / Process glue simple while we
    // stand up Phase 1. We can tighten to strict Swift 6 concurrency later.
    swiftLanguageModes: [.v5]
)
