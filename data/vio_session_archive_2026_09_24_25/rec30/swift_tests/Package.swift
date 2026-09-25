// swift-tools-version:5.9
import PackageDescription
let flags: [SwiftSetting] = [.unsafeFlags(["-swift-version", "5"])]
let package = Package(
    name: "LidarCore",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "LidarCore", swiftSettings: flags),
        .executableTarget(name: "lidar_subset_export", swiftSettings: flags),
        .executableTarget(name: "lidar_writer_ab", swiftSettings: flags),
        .testTarget(name: "LidarCoreTests", dependencies: ["LidarCore"], swiftSettings: flags),
    ]
)
