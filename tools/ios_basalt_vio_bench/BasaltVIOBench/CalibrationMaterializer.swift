import Foundation

enum CalibrationMaterializerError: Error, Equatable {
    case invalidRoot
    case missingArray(String)
    case insufficientCameraEntries(String)
}

enum CalibrationMaterializer {
    /// Produces a deterministic cam0-only calibration from Basalt's pinned
    /// official EuRoC calibration. No numeric field is estimated or changed.
    static func eurocCam0Only(from stereoData: Data) throws -> Data {
        guard var root = try JSONSerialization.jsonObject(with: stereoData) as? [String: Any],
              var value = root["value0"] as? [String: Any] else {
            throw CalibrationMaterializerError.invalidRoot
        }

        for key in ["T_imu_cam", "intrinsics", "resolution", "vignette"] {
            guard let cameras = value[key] as? [Any] else {
                throw CalibrationMaterializerError.missingArray(key)
            }
            guard cameras.count >= 2 else {
                throw CalibrationMaterializerError.insufficientCameraEntries(key)
            }
            value[key] = [cameras[0]]
        }

        root["value0"] = value
        return try JSONSerialization.data(
            withJSONObject: root,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
    }
}
