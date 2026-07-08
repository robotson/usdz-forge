import SwiftUI
import SceneKit

/// Live 3D preview of the produced USDZ — faithful to the old Reality Converter's
/// in-window preview. SceneKit reads USDZ natively, provides free orbit/zoom camera
/// controls out of the box, and autoplays embedded animation, so the user sees
/// exactly what survived the conversion (including whether the animation made it)
/// without leaving the app or trusting Preview.app's buggy viewport.
struct USDZPreviewView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> SCNView {
        let view = SCNView()
        view.allowsCameraControl = true
        view.autoenablesDefaultLighting = true
        view.antialiasingMode = .multisampling4X
        view.backgroundColor = .clear
        view.rendersContinuously = true
        context.coordinator.loadedURL = nil
        load(url, into: view, coordinator: context.coordinator)
        return view
    }

    func updateNSView(_ view: SCNView, context: Context) {
        // Only reload when the file actually changes to avoid resetting the camera.
        guard context.coordinator.loadedURL != url else { return }
        load(url, into: view, coordinator: context.coordinator)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var loadedURL: URL?
    }

    private func load(_ url: URL, into view: SCNView, coordinator: Coordinator) {
        guard let scene = try? SCNScene(url: url, options: [
            .checkConsistency: true,
            .convertToYUp: true
        ]) else {
            view.scene = nil
            return
        }
        view.scene = scene
        view.isPlaying = true // drive the render/animation loop

        // Loop any embedded animation forever so motion is visible in the preview.
        scene.rootNode.enumerateChildNodes { node, _ in
            for key in node.animationKeys {
                if let player = node.animationPlayer(forKey: key) {
                    player.animation.repeatCount = .greatestFiniteMagnitude
                    player.play()
                }
            }
        }
        coordinator.loadedURL = url
    }
}
