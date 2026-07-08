import SwiftUI

@main
struct USDZForgeApp: App {
    var body: some Scene {
        WindowGroup("USDZ Forge") {
            ContentView()
                .frame(minWidth: 560, minHeight: 640)
        }
        .windowResizability(.contentSize)
    }
}
