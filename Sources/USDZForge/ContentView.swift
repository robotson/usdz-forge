import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var status: String = "Drop a .glb, .gltf, or .obj to convert"
    @State private var log: String = ""
    @State private var isConverting = false
    @State private var isTargeted = false
    @State private var lastOutput: URL?
    @State private var animationNote: String?
    @State private var morphWarning = false

    private let engine: ConversionEngine = ContentView.selectEngine()

    /// Resolve the engine root, in priority order:
    ///  1. bundled inside the .app (Contents/Resources/engine) — production
    ///  2. $USDZFORGE_ENGINE_ROOT — explicit dev override
    ///  3. ./engine relative to the working directory — `swift run` from repo root
    private static func selectEngine() -> ConversionEngine {
        var roots: [URL] = []
        if let resources = Bundle.main.resourcePath {
            roots.append(URL(fileURLWithPath: resources).appendingPathComponent("engine"))
        }
        if let override = ProcessInfo.processInfo.environment["USDZFORGE_ENGINE_ROOT"] {
            roots.append(URL(fileURLWithPath: override))
        }
        roots.append(URL(fileURLWithPath: "engine"))

        for root in roots {
            let engine = NativeEngine(engineRoot: root)
            if engine.isAvailable { return engine }
        }
        // Unavailable: surfaces a clear "engine not found" state in the UI.
        return NativeEngine(engineRoot: roots.first ?? URL(fileURLWithPath: "engine"))
    }

    var body: some View {
        VStack(spacing: 18) {
            header
            dropZone
            if let out = lastOutput {
                USDZPreviewView(url: out)
                    .frame(minHeight: 240)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .strokeBorder(Color.secondary.opacity(0.25))
                    )
            }
            statusBlock
            if !log.isEmpty { logView }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var header: some View {
        VStack(spacing: 4) {
            Text("USDZ Forge").font(.system(size: 34, weight: .bold, design: .rounded))
            Text(engine.displayName)
                .font(.caption)
                .foregroundStyle(engine.isAvailable ? AnyShapeStyle(.secondary) : AnyShapeStyle(Color.red))
        }
    }

    private var dropZone: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [9, 6]))
            .foregroundStyle(isTargeted ? Color.accentColor : Color.secondary.opacity(0.6))
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(isTargeted ? Color.accentColor.opacity(0.08) : Color.clear)
            )
            .frame(height: 190)
            .overlay {
                VStack(spacing: 10) {
                    Image(systemName: isConverting ? "gearshape.2.fill" : "cube.transparent")
                        .font(.system(size: 40, weight: .light))
                    Text(isTargeted ? "Release to convert" : "Drag a 3D model here")
                        .font(.headline)
                }
                .foregroundStyle(.secondary)
            }
            .onDrop(of: [.fileURL], isTargeted: $isTargeted) { providers in
                handleDrop(providers)
            }
            .disabled(isConverting)
    }

    private var statusBlock: some View {
        VStack(spacing: 8) {
            if isConverting { ProgressView().controlSize(.small) }
            Text(status)
                .font(.headline)
                .multilineTextAlignment(.center)
            if morphWarning {
                Label("Morph/blendshape animation detected — not supported. Affected meshes will be static in the output.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.orange)
                    .multilineTextAlignment(.center)
            }
            if let note = animationNote {
                Label(note, systemImage: "film.stack")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let out = lastOutput {
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([out])
                } label: {
                    Label("Reveal \(out.lastPathComponent)", systemImage: "folder")
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    private var logView: some View {
        ScrollView {
            Text(log)
                .font(.system(.caption2, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
        }
        .frame(height: 130)
        .background(Color.secondary.opacity(0.08),
                    in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            guard let url else { return }
            DispatchQueue.main.async { convert(url) }
        }
        return true
    }

    private func convert(_ input: URL) {
        isConverting = true
        animationNote = nil
        morphWarning = false
        lastOutput = nil
        status = "Converting \(input.lastPathComponent)…"
        log = ""

        let output = input.deletingPathExtension().appendingPathExtension("usdz")

        DispatchQueue.global(qos: .userInitiated).async {
            let result: Result<ConversionResult, Error>
            do {
                result = .success(try engine.convert(input: input, output: output, options: .init()))
            } catch {
                result = .failure(error)
            }
            DispatchQueue.main.async {
                isConverting = false
                switch result {
                case .success(let r):
                    status = "✅ \(r.outputURL.lastPathComponent)"
                    lastOutput = r.outputURL
                    log = r.log
                    morphWarning = r.morphWarning
                    switch r.hasAnimation {
                    case .some(true):
                        animationNote = "Animation detected — verify in Quick Look on device."
                    case .some(false):
                        animationNote = "No animation in output. If the source was animated, only one clip survives USDZ."
                    case .none:
                        animationNote = nil
                    }
                case .failure(let error):
                    status = "❌ Conversion failed"
                    log = error.localizedDescription
                }
            }
        }
    }
}
