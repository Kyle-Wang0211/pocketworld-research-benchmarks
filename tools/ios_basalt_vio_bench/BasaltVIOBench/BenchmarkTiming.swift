import Foundation

enum LiveBenchmarkDuration {
    static let warmupNanoseconds: UInt64 = 0
    static let measurementNanoseconds: UInt64 = 300_000_000_000
    static let totalNanoseconds = warmupNanoseconds + measurementNanoseconds
}

struct BenchmarkMeasurementWindow: Equatable {
    let startNanoseconds: UInt64
    let endNanoseconds: UInt64

    func contains(captureNanoseconds: UInt64) -> Bool {
        captureNanoseconds >= startNanoseconds && captureNanoseconds < endNanoseconds
    }
}

enum TUMTimestampFormatter {
    static func string(nanoseconds: Int64) -> String {
        precondition(nanoseconds >= 0, "benchmark timestamps must be nonnegative")
        let seconds = nanoseconds / 1_000_000_000
        let remainder = nanoseconds % 1_000_000_000
        return String(format: "%lld.%09lld", seconds, remainder)
    }
}
