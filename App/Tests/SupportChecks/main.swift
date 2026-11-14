import Foundation

// Compile with the actual Support.swift. No XCTest/full Xcode is required.
func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs("FAIL: \(message)\n", stderr); exit(1) }
}
expect(Shell.quote("/path with spaces") == "'/path with spaces'", "Spaces remain literal")
expect(Shell.quote("a'b") == "'a'\\''b'", "Apostrophes are escaped")
expect(Shell.quote("$(touch bad); `echo bad`") == "'$(touch bad); `echo bad`'", "Shell expressions remain literal")
expect(MacOSRelease.all.count == 9, "All nine target releases are selectable")
expect(MacOSRelease.all.first?.legacy == true, "Lion uses legacy restoration")
expect(MacOSRelease.all.first(where: { $0.id == "mavericks" })?.automaticDownload == false, "Mavericks requires local source")
var info: [String: Any] = ["Internal": false, "WholeDisk": true,
    "VirtualOrPhysical": "Physical", "DeviceIdentifier": "disk4",
    "TotalSize": Int64(64_000_000_000), "MediaName": "Test USB", "WritableMedia": true]
func decode() throws -> USBDisk? {
    try USBDisk.decode(PropertyListSerialization.data(fromPropertyList: info, format: .xml, options: 0))
}
do {
    let disk = try decode(); expect(disk?.id == "/dev/disk4", "External whole disk accepted")
    for (key, value) in [("Internal", true as Any), ("WholeDisk", false as Any),
                         ("WritableMedia", false as Any), ("DeviceIdentifier", "disk4s2" as Any)] {
        let previous = info[key]; info[key] = value
        let result = try decode(); expect(result == nil, "Unsafe metadata rejected: \(key)")
        info[key] = previous
    }
    print("Swift checks passed: shell quoting and safe USB metadata parsing.")
} catch { fputs("FAIL: \(error)\n", stderr); exit(1) }
