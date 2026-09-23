import Foundation
import CoreVideo
final class PwXrslamLive {
    static let shared = PwXrslamLive()
    func bindSerialQueue(_ q: DispatchQueue) {}
    func onCameraFrame(_ pb: CVPixelBuffer, ptsSeconds: Double, exposureSeconds: Double) {}
}
