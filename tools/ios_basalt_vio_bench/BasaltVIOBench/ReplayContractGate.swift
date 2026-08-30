import Foundation

enum ReplayContractGate {
    enum ValidationError: Error, Equatable {
        case datasetName(String)
        case cameraCount(Int)
    }

    static let datasetName = "EuRoC_MH_01_easy"
    static let inputCameraCount = 1

    static func validate(datasetName: String, inputCameraCount: Int) throws {
        guard datasetName == Self.datasetName else {
            throw ValidationError.datasetName(datasetName)
        }
        guard inputCameraCount == Self.inputCameraCount else {
            throw ValidationError.cameraCount(inputCameraCount)
        }
    }
}
