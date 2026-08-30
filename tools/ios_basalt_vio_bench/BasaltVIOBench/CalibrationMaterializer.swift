import Foundation

enum CalibrationMaterializerError: Error, Equatable {
    case invalidRoot
    case missingArray(String)
    case insufficientCameraEntries(String)
}

enum CalibrationMaterializer {
    /// Produces a deterministic cam0-only calibration from Basalt's pinned
    /// official EuRoC calibration. No numeric field is estimated or changed.
    /// Builds the calibration a device-recording replay runs on.
    ///
    /// Intrinsics and resolution come from the recording -- `ARFrame.camera.intrinsics`
    /// measured for exactly the frames about to be replayed, cross-checked at
    /// record time. Everything else is carried through from the frozen upstream
    /// calibration unchanged: the IMU-to-camera transform is a rigid mount and is
    /// resolution independent, and the IMU noise model is a property of the
    /// inertial sensor, not of image sampling.
    ///
    /// Nothing here is extrapolated. The alternative -- scaling the frozen 640x480
    /// intrinsics threefold -- is only valid if both formats share a field of
    /// view, which is why it stays a cross-check and never a source.
    static func deviceRecording(
        from frozenData: Data,
        intrinsics: DeviceRecordingIntrinsics,
        width: Int,
        height: Int
    ) throws -> Data {
        guard var root = try JSONSerialization.jsonObject(with: frozenData) as? [String: Any],
              var value0 = root["value0"] as? [String: Any],
              var intrinsicsArray = value0["intrinsics"] as? [[String: Any]],
              !intrinsicsArray.isEmpty,
              var camera = intrinsicsArray[0]["intrinsics"] as? [String: Any] else {
            throw CalibrationMaterializerError.invalidRoot
        }
        camera["fx"] = intrinsics.fx
        camera["fy"] = intrinsics.fy
        camera["cx"] = intrinsics.cx
        camera["cy"] = intrinsics.cy
        intrinsicsArray[0]["intrinsics"] = camera
        value0["intrinsics"] = intrinsicsArray
        value0["resolution"] = [[width, height]]
        root["value0"] = value0
        return try JSONSerialization.data(
            withJSONObject: root,
            options: [.prettyPrinted, .sortedKeys]
        )
    }

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
