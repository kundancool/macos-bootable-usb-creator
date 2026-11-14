import SwiftUI
import AppKit

@main
struct MacOSBootableUSBCreatorApp: App {
    @StateObject private var model = InstallerModel()

    var body: some Scene {
        WindowGroup("macOS Bootable USB Creator") {
            ContentView(model: model)
                .frame(minWidth: 800, minHeight: 650)
                .onAppear { model.refresh() }
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 880, height: 740)
        .commands {
            CommandGroup(replacing: .newItem) { }
            CommandGroup(replacing: .appTermination) {
                Button("Quit macOS Bootable USB Creator") { NSApplication.shared.terminate(nil) }
                    .keyboardShortcut("q").disabled(model.busy)
            }
            CommandGroup(after: .help) {
                Button("Open guide") { model.openGuide() }
            }
        }
    }
}

@MainActor
final class InstallerModel: ObservableObject {
    @Published var disks: [USBDisk] = []
    @Published var selectedDisk = ""
    @Published var busy = false
    @Published var status = "Choose a macOS version and an installer source to begin."
    @Published var error: String?
    @Published var log = ""
    @Published var installerReady = false
    @Published var repairMode = false
    @Published var showConfirmation = false
    @Published var showLog = false
    @Published var selectedRelease = "catalina"
    @Published var useLocalSource = false
    @Published var sourceURL: URL?
    @Published var progressFraction: Double?
    @Published var progressTitle = "Ready"
    @Published var workURL: URL
    @Published var python: String?
    @Published var toolsReady = false
    private var task: Process?
    private var monitor: Timer?
    private var outputPipe: Pipe?

    init() {
        let fallback = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/MacOSBootableUSBCreator", isDirectory: true)
        workURL = URL(fileURLWithPath: UserDefaults.standard.string(forKey: "workDirectory") ?? fallback.path)
        python = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    var backend: URL? { Bundle.main.resourceURL?.appendingPathComponent("backend/macos_usb.py") }
    var release: MacOSRelease { MacOSRelease.all.first { $0.id == selectedRelease }! }
    var releaseWorkURL: URL { workURL.appendingPathComponent(selectedRelease) }
    var selected: USBDisk? { disks.first { $0.id == selectedDisk } }
    var freeSpace: String {
        guard let attributes = try? FileManager.default.attributesOfFileSystem(forPath: workURL.path),
              let bytes = attributes[.systemFreeSize] as? Int64 else { return "Available space is checked before download." }
        return ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file) + " available"
    }

    func append(_ text: String) {
        log = String((log + text).suffix(64_000))
        updateProgress(log)
    }

    func updateProgress(_ text: String) {
        for line in text.components(separatedBy: .newlines).reversed() where line.hasPrefix("::progress::") {
            guard let data = String(line.dropFirst("::progress::".count)).data(using: .utf8),
                  let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            progressTitle = event["detail"] as? String ?? event["stage"] as? String ?? "Working"
            if let current = event["current"] as? Double, let total = event["total"] as? Double, total > 0 {
                progressFraction = min(1, max(0, current / total))
            } else {
                progressFraction = nil
                if event["stage"] as? String == "download", let current = event["current"] as? Int64 {
                    progressTitle += " · " + ByteCountFormatter.string(fromByteCount: current, countStyle: .file)
                }
            }
            break
        }
    }

    var failureSummary: String {
        log.components(separatedBy: .newlines).last(where: { $0.hasPrefix("ERROR:") })?
            .replacingOccurrences(of: "ERROR: ", with: "")
        ?? "The operation did not finish. The activity log shows the exact error and next step."
    }

    func refresh() {
        let marker = release.legacy ? "Contents/SharedSupport/InstallESD.dmg" : "Contents/Resources/createinstallmedia"
        installerReady = FileManager.default.fileExists(atPath: releaseWorkURL.appendingPathComponent(release.appName + "/" + marker).path)
        guard !busy else { return }
        let previous = selectedDisk
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Result { try Command.disks() }
            let developerTools = (try? Command.capture("/usr/bin/xcode-select", ["-p"]).status) == 0
            DispatchQueue.main.async {
                self.toolsReady = developerTools
                switch result {
                case .success(let disks):
                    self.disks = disks
                    self.selectedDisk = disks.contains { $0.id == previous } ? previous : ""
                case .failure(let error):
                    self.disks = []
                    self.selectedDisk = ""
                    self.error = error.localizedDescription
                }
            }
        }
    }

    func chooseFolder() {
        guard !busy else { return }
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.prompt = "Use folder"
        panel.message = "Choose a folder on your internal drive. Downloads and installer files stay here."
        if panel.runModal() == .OK, let url = panel.url {
            if (try? url.resourceValues(forKeys: [.volumeIsInternalKey]).volumeIsInternal) != true {
                error = "Choose a folder on the internal drive. The USB must be separate from your installer files."
                return
            }
            workURL = url
            UserDefaults.standard.set(url.path, forKey: "workDirectory")
            refresh()
        }
    }

    func chooseSource() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.treatsFilePackagesAsDirectories = false
        panel.prompt = "Use installer"
        panel.message = "Choose an original full installer .app, Apple's installer .dmg, or .pkg for \(release.title)."
        if panel.runModal() == .OK { sourceURL = panel.url }
    }

    func prepare(filesOnly: Bool = false) {
        guard !busy, let python, let backend else { return }
        error = nil
        do {
            try FileManager.default.createDirectory(at: workURL, withIntermediateDirectories: true)
            let process = Process()
            let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: python)
            var arguments = [backend.path, "download", "--macos", selectedRelease]
            if useLocalSource {
                guard let sourceURL else { throw NSError(domain: "MacOSBootableUSBCreator", code: 3, userInfo: [NSLocalizedDescriptionKey: "Choose a local full installer first."]) }
                arguments += ["--source", sourceURL.path]
            }
            if filesOnly { arguments.append("--download-files-only") }
            process.arguments = arguments
            var environment = ProcessInfo.processInfo.environment
            environment["MACOS_USB_WORKDIR"] = workURL.path
            environment["MACOS_USB_EVENTS"] = "1"
            environment["PYTHONUNBUFFERED"] = "1"
            process.environment = environment
            process.standardOutput = pipe
            process.standardError = pipe
            outputPipe = pipe
            pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard !data.isEmpty else { handle.readabilityHandler = nil; return }
                let text = String(decoding: data, as: UTF8.self)
                DispatchQueue.main.async { self?.append(text) }
            }
            process.terminationHandler = { [weak self] process in
                DispatchQueue.main.async {
                    guard let self else { return }
                    self.busy = false
                    self.task = nil
                    self.status = process.terminationStatus == 0 ? (filesOnly ? "Downloads saved. Prepare the installer when you are ready to create USB media." : "Installer prepared. Select your USB to continue.") : "Preparation stopped. Your existing downloads are kept."
                    if process.terminationStatus != 0 { self.error = self.failureSummary; self.showLog = true }
                    self.refresh()
                }
            }
            status = "Preparing installer. Keep this window open; existing valid files will be reused."
            progressTitle = filesOnly ? "Starting Apple download" : "Starting installer preparation"
            progressFraction = nil
            busy = true
            task = process
            try process.run()
        } catch {
            busy = false
            task = nil
            self.error = error.localizedDescription
        }
    }

    func openTerminalWorkflow(checkOnly: Bool = false) {
        guard !busy, let python, let backend, let disk = selected else { return }
        error = nil
        do {
            // Recheck the selected device before launching; backend rechecks before writing.
            guard try Command.disks().contains(disk) else {
                throw NSError(domain: "MacOSBootableUSBCreator", code: 2, userInfo: [NSLocalizedDescriptionKey: "The selected USB changed. Refresh and select it again."])
            }
            let logs = workURL.appendingPathComponent("logs", isDirectory: true)
            try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
            let id = UUID().uuidString
            let script = logs.appendingPathComponent("workflow-\(id).command")
            let output = logs.appendingPathComponent("workflow-\(id).log")
            let completion = logs.appendingPathComponent("workflow-\(id).status")
            var arguments = [python, backend.path, "all", "--macos", selectedRelease, "--disk", disk.id]
            if checkOnly { arguments.append("--check-only") }
            else if repairMode { arguments.append("--repair-usb") }
            let command = arguments.map(Shell.quote).joined(separator: " ")
            let body = """
            #!/bin/bash
            set -o pipefail
            finish() { printf '%s\\n' "$?" > \(Shell.quote(completion.path)); }
            trap finish EXIT
            trap 'exit 130' INT TERM HUP
            export MACOS_USB_WORKDIR=\(Shell.quote(workURL.path))
            export MACOS_USB_EVENTS=1
            export PYTHONUNBUFFERED=1
            \(command) 2>&1 | /usr/bin/tee \(Shell.quote(output.path))
            result=${PIPESTATUS[0]}
            printf '%s\\n' "$result" > \(Shell.quote(completion.path))
            printf '\\nFinished with exit code %s. You can close this Terminal window.\\n' "$result"
            exit "$result"
            """
            try body.write(to: script, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: script.path)
            busy = true
            status = checkOnly ? "Checking USB in Terminal. No disk will be erased." : "Continue in Terminal for confirmation and your administrator password."
            progressTitle = "Waiting for Terminal"
            progressFraction = nil
            let terminal = URL(fileURLWithPath: "/System/Applications/Utilities/Terminal.app")
            NSWorkspace.shared.open([script], withApplicationAt: terminal, configuration: .init()) { _, error in
                if let error {
                    DispatchQueue.main.async { self.busy = false; self.monitor?.invalidate(); self.error = error.localizedDescription }
                }
            }
            monitor = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
                DispatchQueue.main.async {
                    guard let self else { return }
                    if let text = try? String(contentsOf: output, encoding: .utf8) { self.log = String(text.suffix(64_000)); self.updateProgress(self.log) }
                    if let text = try? String(contentsOf: completion, encoding: .utf8) {
                        self.monitor?.invalidate()
                        self.busy = false
                        let success = text.trimmingCharacters(in: .whitespacesAndNewlines) == "0"
                        self.status = success ? (checkOnly ? "USB checks passed. No disk was erased." : "Finished. Read the Terminal result, then eject the USB.") : "The operation stopped. Your installer download is kept."
                        if !success { self.error = self.failureSummary; self.showLog = true }
                        self.refresh()
                    }
                }
            }
        } catch { self.error = error.localizedDescription }
    }

    func openGuide() {
        if let url = Bundle.main.resourceURL?.appendingPathComponent("README.md") { NSWorkspace.shared.open(url) }
    }

    func revealFiles() {
        try? FileManager.default.createDirectory(at: workURL, withIntermediateDirectories: true)
        NSWorkspace.shared.open(workURL)
    }

    func copyLog() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString("macOS Bootable USB Creator 0.1.0\nmacOS: \(ProcessInfo.processInfo.operatingSystemVersionString)\n\(log)", forType: .string)
    }
}
