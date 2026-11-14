import SwiftUI
import AppKit

private let ocean = Color(red: 0.09, green: 0.34, blue: 0.42)

struct ContentView: View {
    @ObservedObject var model: InstallerModel

    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 22) {
                if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
                   let image = NSImage(contentsOf: url) {
                    Image(nsImage: image).resizable().frame(width: 100, height: 100).accessibilityHidden(true)
                } else {
                    Image(systemName: "externaldrive.fill").font(.system(size: 48, weight: .light)).foregroundStyle(ocean)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("macOS Bootable USB Creator").font(.system(size: 25, weight: .semibold))
                    Text("Lion through Catalina.\nChoose your installer.")
                        .font(.system(size: 15)).foregroundStyle(.secondary)
                }
                Divider()
                Label("Apple downloads", systemImage: "arrow.down.circle")
                Label("Your USB, your choice", systemImage: "externaldrive")
                Label("Original installer restored", systemImage: "checkmark.shield")
                Spacer()
                Button("Read the guide") { model.openGuide() }.buttonStyle(.link)
                Text("0.1.0 · macOS 10.7–10.15")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .font(.system(size: 12))
            .padding(28)
            .frame(width: 245, alignment: .leading)
            .frame(maxHeight: .infinity)
            .background(ocean.opacity(0.06))

            ScrollView {
                VStack(alignment: .leading, spacing: 23) {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(model.repairMode ? "Repair an existing installer" : "Make your installer")
                            .font(.system(size: 28, weight: .semibold))
                        Text(model.repairMode ? "Restore original Apple installer code without erasing the USB. Keep the matching original downloads." : "Download or import an installer here. Use the finished USB on a compatible Intel Mac. This does not install macOS on your current Mac.")
                            .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                    Picker("Workflow", selection: $model.repairMode) {
                        Text("Create USB").tag(false)
                        Text("Repair USB").tag(true)
                    }.pickerStyle(.segmented).disabled(model.busy)
                    Picker("macOS version", selection: $model.selectedRelease) {
                        ForEach(MacOSRelease.all) { release in
                            Text("\(release.title)  \(release.version)").tag(release.id)
                        }
                    }.disabled(model.busy)
                    if model.release.legacy {
                        Text("This release uses legacy disk-image restoration. Modern-host compatibility varies; this path needs hardware validation. Signature repair does not apply.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if !model.repairMode {
                        Picker("Installer source", selection: $model.useLocalSource) {
                            Text("Download from Apple").tag(false)
                            Text("Use a local installer").tag(true)
                        }.disabled(model.busy)
                        if !model.release.automaticDownload && !model.useLocalSource {
                            Text("Apple does not publish a direct Mavericks download here. Choose a local original installer. No unofficial mirror will be used.")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                        if model.useLocalSource {
                            HStack {
                                Text(model.sourceURL?.lastPathComponent ?? "Select a full .app, Apple .dmg, or .pkg")
                                    .lineLimit(2).font(.caption).foregroundStyle(.secondary)
                                Spacer()
                                Button("Choose installer…") { model.chooseSource() }.disabled(model.busy)
                            }
                        }
                    }

                    if model.python == nil || !model.toolsReady {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("One-time setup", systemImage: "wrench.and.screwdriver")
                                .font(.headline)
                            if model.python == nil {
                                Text("Install Python 3.9 or newer, then reopen this app.")
                                Link("Get Python for macOS", destination: URL(string: "https://www.python.org/downloads/macos/")!)
                            }
                            if !model.toolsReady {
                                Text("Install Apple Command Line Tools by running xcode-select --install in Terminal. Then refresh.")
                            }
                        }.padding(14).background(Color.orange.opacity(0.1), in: RoundedRectangle(cornerRadius: 10))
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Label("Installer files", systemImage: model.installerReady ? "checkmark.circle.fill" : "arrow.down.circle")
                                .font(.headline)
                            Spacer()
                            Text(model.installerReady ? "Prepared" : "Not prepared").foregroundStyle(.secondary)
                        }
                        Text(model.workURL.path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        HStack {
                            Text(model.freeSpace).font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button("Change folder…") { model.chooseFolder() }.disabled(model.busy)
                        }
                        if !model.repairMode {
                            HStack {
                                Button(model.installerReady ? "Check prepared installer" : "Prepare installer") { model.prepare() }
                                    .disabled(model.busy || model.python == nil || !model.toolsReady || (!model.useLocalSource && !model.release.automaticDownload) || (model.useLocalSource && model.sourceURL == nil && !model.installerReady))
                                if !model.useLocalSource && model.release.automaticDownload {
                                    Button("Download files only") { model.prepare(filesOnly: true) }
                                        .disabled(model.busy || model.python == nil || !model.toolsReady)
                                }
                            }
                        }
                    }
                    Divider()
                    VStack(alignment: .leading, spacing: 11) {
                        HStack {
                            Label("USB drive", systemImage: "externaldrive.badge.plus").font(.headline)
                            Spacer()
                            Button("Refresh") { model.refresh() }.disabled(model.busy)
                        }
                        Picker("Choose USB", selection: $model.selectedDisk) {
                            Text("Select an external drive…").tag("")
                            ForEach(model.disks) { disk in Text(disk.label).tag(disk.id) }
                        }.labelsHidden().disabled(model.busy)
                        if model.disks.isEmpty {
                            Text("Connect a USB drive of at least 16 GB, then refresh. Internal disks are never listed.")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                        Text(model.repairMode ? "Repair replaces installer code and signatures. It keeps the existing USB payload and cannot fix an incomplete copy." : "Creating the installer erases the selected USB. Back up any files on it first.")
                            .font(.callout).foregroundStyle(model.repairMode ? .secondary : .primary)
                    }
                    HStack {
                        Button("Check USB") { model.openTerminalWorkflow(checkOnly: true) }
                            .disabled(model.busy || model.selected == nil || !model.installerReady || model.python == nil || !model.toolsReady)
                        Spacer()
                        Button(model.repairMode ? "Repair USB…" : "Create installer…") { model.showConfirmation = true }
                            .buttonStyle(.borderedProminent).tint(ocean)
                            .disabled(model.busy || model.selected == nil || (!model.installerReady && !model.repairMode) || model.python == nil || !model.toolsReady || (model.repairMode && model.release.legacy))
                    }
                    Text("USB actions open Terminal for disk confirmation and your administrator password. The app never reads or stores that password.")
                        .font(.caption).foregroundStyle(.secondary)
                    Divider()
                    HStack(alignment: .top, spacing: 12) {
                        if model.busy { ProgressView().controlSize(.small) }
                        Text(model.status).font(.callout).textSelection(.enabled)
                    }
                    if model.busy {
                        VStack(alignment: .leading, spacing: 7) {
                            HStack {
                                Text(model.progressTitle).font(.caption).lineLimit(2)
                                Spacer()
                                if let fraction = model.progressFraction {
                                    Text("\(Int(fraction * 100))%").font(.caption).monospacedDigit()
                                }
                            }
                            if let fraction = model.progressFraction {
                                ProgressView(value: fraction).tint(ocean)
                            } else {
                                Text("Working — this step does not report a measurable percentage.")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    }
                    if let error = model.error {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(.callout).foregroundStyle(.red).textSelection(.enabled)
                    }
                    DisclosureGroup("Activity log", isExpanded: $model.showLog) {
                        ScrollView {
                            Text(model.log.isEmpty ? "Activity appears here when a task starts." : model.log)
                                .font(.system(size: 11, design: .monospaced))
                                .frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
                        }.frame(height: 150)
                        HStack {
                            Button("Copy log") { model.copyLog() }
                            Button("Open files") { model.revealFiles() }
                            Spacer()
                        }
                    }
                }.padding(32)
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .onChange(of: model.selectedRelease) { _ in
            model.sourceURL = nil
            model.useLocalSource = !model.release.automaticDownload
            model.refresh()
        }
        .alert(model.repairMode ? "Repair this installer?" : "Erase this USB and create an installer?", isPresented: $model.showConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Continue in Terminal", role: model.repairMode ? nil : .destructive) { model.openTerminalWorkflow() }
        } message: {
            Text((model.selected?.label ?? "No disk selected") + (model.repairMode ? "\nOriginal installer code will be restored. The USB will not be erased." : "\nAll files on this USB will be erased. Terminal will ask you to type the disk identifier before writing."))
        }
    }
}
