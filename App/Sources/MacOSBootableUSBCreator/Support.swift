import Foundation

struct MacOSRelease: Identifiable, Hashable {
    let id: String
    let title: String
    let version: String
    let appName: String
    let automaticDownload: Bool
    var legacy: Bool { id == "lion" || id == "mountain-lion" }
    static let all: [MacOSRelease] = [
        .init(id: "lion", title: "Lion", version: "10.7", appName: "Install Mac OS X Lion.app", automaticDownload: true),
        .init(id: "mountain-lion", title: "Mountain Lion", version: "10.8", appName: "Install OS X Mountain Lion.app", automaticDownload: true),
        .init(id: "mavericks", title: "Mavericks", version: "10.9", appName: "Install OS X Mavericks.app", automaticDownload: false),
        .init(id: "yosemite", title: "Yosemite", version: "10.10", appName: "Install OS X Yosemite.app", automaticDownload: true),
        .init(id: "el-capitan", title: "El Capitan", version: "10.11", appName: "Install OS X El Capitan.app", automaticDownload: true),
        .init(id: "sierra", title: "Sierra", version: "10.12", appName: "Install macOS Sierra.app", automaticDownload: true),
        .init(id: "high-sierra", title: "High Sierra", version: "10.13", appName: "Install macOS High Sierra.app", automaticDownload: true),
        .init(id: "mojave", title: "Mojave", version: "10.14", appName: "Install macOS Mojave.app", automaticDownload: true),
        .init(id: "catalina", title: "Catalina", version: "10.15", appName: "Install macOS Catalina.app", automaticDownload: true)
    ]
}

enum Shell {
    static func quote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}

struct USBDisk: Identifiable, Hashable {
    let id: String
    let name: String
    let bytes: Int64

    var label: String {
        "\(name) — \(ByteCountFormatter.string(fromByteCount: bytes, countStyle: .decimal)) (\(id))"
    }

    static func decode(_ data: Data) throws -> USBDisk? {
        guard let info = try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
              info["Internal"] as? Bool == false,
              info["WholeDisk"] as? Bool == true,
              info["VirtualOrPhysical"] as? String == "Physical",
              info["WritableMedia"] as? Bool == true,
              let identifier = info["DeviceIdentifier"] as? String,
              identifier.range(of: "^disk[0-9]+$", options: .regularExpression) != nil,
              let bytes = info["TotalSize"] as? Int64, bytes >= 16_000_000_000 else { return nil }
        return USBDisk(id: "/dev/" + identifier,
                       name: info["MediaName"] as? String ?? identifier, bytes: bytes)
    }
}

struct CommandResult {
    let status: Int32
    let data: Data
}

enum Command {
    static func capture(_ executable: String, _ arguments: [String]) throws -> CommandResult {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return CommandResult(status: process.terminationStatus, data: data)
    }

    static func disks() throws -> [USBDisk] {
        let list = try capture("/usr/sbin/diskutil", ["list", "-plist", "external", "physical"])
        guard list.status == 0,
              let plist = try PropertyListSerialization.propertyList(from: list.data, format: nil) as? [String: Any],
              let devices = plist["AllDisksAndPartitions"] as? [[String: Any]] else {
            throw NSError(domain: "MacOSBootableUSBCreator", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Could not read external drives. Reconnect the USB and refresh."])
        }
        return try devices.compactMap { device in
            guard let identifier = device["DeviceIdentifier"] as? String else { return nil }
            let info = try capture("/usr/sbin/diskutil", ["info", "-plist", identifier])
            return info.status == 0 ? try USBDisk.decode(info.data) : nil
        }
    }
}
