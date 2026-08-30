import Foundation

enum LiveBenchmarkDuration {
    static let warmupNanoseconds: UInt64 = 0

    /// The frozen product duration. Never changed by a run.
    static let contractMeasurementNanoseconds: UInt64 = 300_000_000_000

    /// What the current run measures for.
    ///
    /// Only the self-test harness shortens this, so the record path can be
    /// driven end to end from the command line without spending five minutes and
    /// 23 GiB per attempt. Any run whose value differs from the contract's is
    /// receipted as such and can never be a scored result.
    nonisolated(unsafe) static var measurementNanoseconds: UInt64 =
        contractMeasurementNanoseconds

    static var isContractDuration: Bool {
        measurementNanoseconds == contractMeasurementNanoseconds
    }

    static var totalNanoseconds: UInt64 { warmupNanoseconds + measurementNanoseconds }
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
