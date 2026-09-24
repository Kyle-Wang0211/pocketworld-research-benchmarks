// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.
//
// Generated file. Do not edit.
//

import PackageDescription

let package = Package(
    name: "FlutterGeneratedPluginSwiftPackage",
    platforms: [
        .iOS("15.0")
    ],
    products: [
        .library(name: "FlutterGeneratedPluginSwiftPackage", type: .static, targets: ["FlutterGeneratedPluginSwiftPackage"])
    ],
    dependencies: [
        .package(name: "app_links", path: "../.packages/app_links-7.0.0"),
        .package(name: "background_downloader", path: "../.packages/background_downloader-9.5.4"),
        .package(name: "camera_avfoundation", path: "../.packages/camera_avfoundation-0.10.1"),
        .package(name: "file_picker", path: "../.packages/file_picker-8.3.7"),
        .package(name: "flutter_secure_storage_darwin", path: "../.packages/flutter_secure_storage_darwin-0.3.2"),
        .package(name: "image_picker_ios", path: "../.packages/image_picker_ios-0.8.13+7"),
        .package(name: "integration_test", path: "../.packages/integration_test"),
        .package(name: "path_provider_foundation", path: "../.packages/path_provider_foundation-2.5.1"),
        .package(name: "sensors_plus", path: "../.packages/sensors_plus-7.0.0"),
        .package(name: "shared_preferences_foundation", path: "../.packages/shared_preferences_foundation-2.5.6"),
        .package(name: "url_launcher_ios", path: "../.packages/url_launcher_ios-6.4.1"),
        .package(name: "FlutterFramework", path: "../.packages/FlutterFramework")
    ],
    targets: [
        .target(
            name: "FlutterGeneratedPluginSwiftPackage",
            dependencies: [
                .product(name: "app-links", package: "app_links"),
                .product(name: "background-downloader", package: "background_downloader"),
                .product(name: "camera-avfoundation", package: "camera_avfoundation"),
                .product(name: "file-picker", package: "file_picker"),
                .product(name: "flutter-secure-storage-darwin", package: "flutter_secure_storage_darwin"),
                .product(name: "image-picker-ios", package: "image_picker_ios"),
                .product(name: "integration-test", package: "integration_test"),
                .product(name: "path-provider-foundation", package: "path_provider_foundation"),
                .product(name: "sensors-plus", package: "sensors_plus"),
                .product(name: "shared-preferences-foundation", package: "shared_preferences_foundation"),
                .product(name: "url-launcher-ios", package: "url_launcher_ios"),
                .product(name: "FlutterFramework", package: "FlutterFramework")
            ]
        )
    ]
)
