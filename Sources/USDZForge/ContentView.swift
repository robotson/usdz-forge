import SwiftUI
import UniformTypeIdentifiers

// MARK: - Batch model

struct BatchItem: Identifiable {
    enum State {
        case pending
        case converting
        case done(ConversionResult)
        case failed(String)
        case skipped   // output already exists (overwrite off)
        case cancelled
    }

    let id = UUID()
    let input: URL
    var state: State = .pending

    var output: URL? {
        if case .done(let r) = state { return r.outputURL }
        return nil
    }
    var result: ConversionResult? {
        if case .done(let r) = state { return r }
        return nil
    }
}

// MARK: - View

struct ContentView: View {
    /// Read from the background batch loop, set on the main thread.
    private final class CancelToken {
        var isCancelled = false
    }

    @State private var items: [BatchItem] = []
    @State private var selectedItemID: UUID?
    @State private var isConverting = false
    @State private var isTargeted = false
    @State private var availableUpdate: UpdateChecker.Update?
    @State private var overwriteExisting = false
    @State private var cancelToken = CancelToken()

    private static let modelExtensions: Set<String> = ["glb", "gltf", "obj"]

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

    /// True when the x86_64 slice is executing — i.e. an Intel Mac (the arm64
    /// slice always wins on Apple Silicon). The bundled Python/USD engine is
    /// arm64-only, so conversion can't work here; say so instead of failing
    /// with an opaque spawn error.
    private var isIntelHost: Bool {
        #if arch(x86_64)
        return true
        #else
        return false
        #endif
    }

    private var selectedItem: BatchItem? {
        if let id = selectedItemID, let item = items.first(where: { $0.id == id }) {
            return item
        }
        return items.last(where: { $0.output != nil })
    }

    var body: some View {
        VStack(spacing: 16) {
            header
            dropZone
            controlsRow
            if let out = selectedItem?.output {
                USDZPreviewView(url: out)
                    .frame(minHeight: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .strokeBorder(Color.secondary.opacity(0.25))
                    )
            }
            statusBlock
            if items.count > 1 { batchList }
            if let log = selectedItem?.result?.log, !log.isEmpty { logView(log) }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .safeAreaInset(edge: .top, spacing: 0) {
            if let update = availableUpdate {
                updateBanner(update)
            }
        }
        .task {
            availableUpdate = await UpdateChecker.check()
        }
    }

    // MARK: header / drop zone

    private var header: some View {
        VStack(spacing: 4) {
            Text("USDZ Forge").font(.system(size: 34, weight: .bold, design: .rounded))
            if isIntelHost {
                Label("Intel Mac detected — this build's conversion engine requires Apple Silicon (M1 or newer). See the GitHub README for alternatives.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.orange)
                    .multilineTextAlignment(.center)
            } else {
                Text(engine.displayName)
                    .font(.caption)
                    .foregroundStyle(engine.isAvailable ? AnyShapeStyle(.secondary) : AnyShapeStyle(Color.red))
            }
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
            .frame(height: items.isEmpty ? 170 : 90)
            .overlay {
                VStack(spacing: 8) {
                    Image(systemName: isConverting ? "gearshape.2.fill" : "cube.transparent")
                        .font(.system(size: items.isEmpty ? 38 : 24, weight: .light))
                    Text(isTargeted ? "Release to convert"
                         : "Drag 3D models here — files or folders")
                        .font(items.isEmpty ? .headline : .subheadline)
                }
                .foregroundStyle(.secondary)
            }
            .onDrop(of: [.fileURL], isTargeted: $isTargeted) { providers in
                handleDrop(providers)
            }
            .disabled(isConverting || isIntelHost)
            .animation(.default, value: items.isEmpty)
    }

    private var controlsRow: some View {
        HStack {
            Toggle("Overwrite existing .usdz files", isOn: $overwriteExisting)
                .toggleStyle(.checkbox)
                .font(.caption)
                .disabled(isConverting)
                .help("Off: files whose .usdz already exists are skipped — handy when re-running a folder.")
            Spacer()
            if isConverting {
                Button(role: .destructive) {
                    cancelToken.isCancelled = true
                } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
                .controlSize(.small)
            }
        }
    }

    // MARK: status + batch list

    private var summary: (done: Int, failed: Int, warned: Int, skipped: Int) {
        var done = 0, failed = 0, warned = 0, skipped = 0
        for item in items {
            switch item.state {
            case .done(let r):
                done += 1
                if r.morphWarning { warned += 1 }
            case .failed: failed += 1
            case .skipped: skipped += 1
            default: break
            }
        }
        return (done, failed, warned, skipped)
    }

    private var statusBlock: some View {
        VStack(spacing: 8) {
            if isConverting { ProgressView().controlSize(.small) }

            if items.count > 1 {
                let s = summary
                Text("Converted \(s.done)/\(items.count)"
                     + (s.failed > 0 ? " · \(s.failed) failed" : "")
                     + (s.skipped > 0 ? " · \(s.skipped) skipped" : "")
                     + (s.warned > 0 ? " · \(s.warned) morph warning\(s.warned == 1 ? "" : "s")" : ""))
                    .font(.headline)
            } else if let item = items.first {
                singleStatus(item)
            } else {
                Text("Drop .glb, .gltf, or .obj files to convert")
                    .font(.headline)
            }

            if let result = selectedItem?.result {
                if result.morphWarning {
                    Label("Morph/blendshape animation detected — not supported. Affected meshes will be static in the output.",
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.orange)
                        .multilineTextAlignment(.center)
                }
                switch result.hasAnimation {
                case .some(true):
                    Label("Animation detected — verify in Quick Look on device.",
                          systemImage: "film.stack")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                case .some(false):
                    Label("No animation in output.", systemImage: "film.stack")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                case .none:
                    EmptyView()
                }
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([result.outputURL])
                } label: {
                    Label("Reveal \(result.outputURL.lastPathComponent)", systemImage: "folder")
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    @ViewBuilder
    private func singleStatus(_ item: BatchItem) -> some View {
        switch item.state {
        case .pending, .converting:
            Text("Converting \(item.input.lastPathComponent)…").font(.headline)
        case .done(let r):
            Text("✅ \(r.outputURL.lastPathComponent)").font(.headline)
        case .failed(let message):
            VStack(spacing: 4) {
                Text("❌ \(item.input.lastPathComponent) failed").font(.headline)
                Text(message)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(6)
                    .textSelection(.enabled)
            }
        case .skipped:
            Text("⏭ \(item.input.lastPathComponent) skipped — output already exists")
                .font(.headline)
        case .cancelled:
            Text("🛑 \(item.input.lastPathComponent) cancelled").font(.headline)
        }
    }

    private var batchList: some View {
        ScrollView {
            VStack(spacing: 2) {
                ForEach(items) { item in
                    batchRow(item)
                }
            }
        }
        .frame(maxHeight: 190)
        .background(Color.secondary.opacity(0.06),
                    in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func batchRow(_ item: BatchItem) -> some View {
        Button {
            selectedItemID = item.id
        } label: {
            HStack(spacing: 8) {
                switch item.state {
                case .pending:
                    Image(systemName: "circle.dotted").foregroundStyle(.secondary)
                case .converting:
                    ProgressView().controlSize(.mini)
                case .done(let r):
                    Image(systemName: r.morphWarning
                          ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                        .foregroundStyle(r.morphWarning ? .orange : .green)
                case .failed:
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
                case .skipped:
                    Image(systemName: "arrow.right.to.line.circle").foregroundStyle(.secondary)
                case .cancelled:
                    Image(systemName: "slash.circle").foregroundStyle(.secondary)
                }
                Text(item.input.lastPathComponent)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
                if case .done(let r) = item.state, r.hasAnimation == true {
                    Image(systemName: "film.stack")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .help("Animation present")
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                selectedItemID == item.id ? Color.accentColor.opacity(0.12) : Color.clear,
                in: RoundedRectangle(cornerRadius: 6, style: .continuous)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func logView(_ log: String) -> some View {
        ScrollView {
            Text(log)
                .font(.system(.caption2, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
        }
        .frame(height: 110)
        .background(Color.secondary.opacity(0.08),
                    in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    /// Pinned flush to the top of the window (safeAreaInset), not floated in
    /// the centered content stack.
    private func updateBanner(_ update: UpdateChecker.Update) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "arrow.down.circle.fill")
                .foregroundStyle(Color.accentColor)
            Text("USDZ Forge \(update.version) is available")
                .font(.callout.weight(.medium))
            Spacer()
            Button("Download") { NSWorkspace.shared.open(update.url) }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            Button {
                withAnimation { availableUpdate = nil }
            } label: {
                Image(systemName: "xmark").font(.caption2)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity)
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
        .transition(.move(edge: .top).combined(with: .opacity))
    }

    // MARK: drop handling + batch runner

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard !providers.isEmpty else { return false }
        let group = DispatchGroup()
        var dropped: [URL] = []
        let lock = NSLock()

        for provider in providers {
            group.enter()
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                if let url {
                    lock.lock(); dropped.append(url); lock.unlock()
                }
                group.leave()
            }
        }
        group.notify(queue: .main) {
            startBatch(expandToModelFiles(dropped))
        }
        return true
    }

    /// Files pass through; folders are scanned RECURSIVELY for model files.
    /// Outputs are written next to their inputs, so a converted folder tree
    /// mirrors itself automatically.
    private func expandToModelFiles(_ urls: [URL]) -> [URL] {
        var files: [URL] = []
        let fm = FileManager.default
        for url in urls {
            var isDir: ObjCBool = false
            guard fm.fileExists(atPath: url.path, isDirectory: &isDir) else { continue }
            if isDir.boolValue {
                let enumerator = fm.enumerator(
                    at: url, includingPropertiesForKeys: nil,
                    options: [.skipsHiddenFiles, .skipsPackageDescendants])
                var found: [URL] = []
                while let child = enumerator?.nextObject() as? URL {
                    if Self.modelExtensions.contains(child.pathExtension.lowercased()) {
                        found.append(child)
                    }
                }
                files.append(contentsOf: found.sorted { $0.path < $1.path })
            } else if Self.modelExtensions.contains(url.pathExtension.lowercased()) {
                files.append(url)
            }
        }
        return files
    }

    private func startBatch(_ urls: [URL]) {
        guard !urls.isEmpty, !isConverting else { return }
        items = urls.map { BatchItem(input: $0) }
        selectedItemID = nil
        isConverting = true
        let token = CancelToken()
        cancelToken = token
        let overwrite = overwriteExisting

        // Sequential but off the main thread: one bad file must never sink the
        // run — every failure is caught, recorded, and the batch continues.
        DispatchQueue.global(qos: .userInitiated).async {
            for index in items.indices {
                let input = items[index].input
                let output = input.deletingPathExtension().appendingPathExtension("usdz")

                if token.isCancelled {
                    DispatchQueue.main.async { items[index].state = .cancelled }
                    continue
                }
                if !overwrite && FileManager.default.fileExists(atPath: output.path) {
                    DispatchQueue.main.async { items[index].state = .skipped }
                    continue
                }

                DispatchQueue.main.async { items[index].state = .converting }
                let newState: BatchItem.State
                do {
                    let result = try engine.convert(input: input, output: output, options: .init())
                    newState = .done(result)
                } catch {
                    newState = .failed(error.localizedDescription)
                }
                DispatchQueue.main.async { items[index].state = newState }
            }
            DispatchQueue.main.async { isConverting = false }
        }
    }
}
