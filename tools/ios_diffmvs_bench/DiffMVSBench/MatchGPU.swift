import Foundation
import Metal

// GPU counterpart to the C++ pw_bench_match (NativeBench.cpp): brute-force
// 128-d L2 descriptor matching, nearest + Lowe ratio 0.7, one thread per
// query descriptor. Builds random normalized descriptors (same setup as the
// CPU kernel), dispatches the compute pass `numPairs` times, and returns the
// total wall-clock milliseconds. Each dispatch is GPU-synchronized via
// commandBuffer.waitUntilCompleted(), so the timer reflects real GPU work.
//
// Returns -1.0 on any Metal setup failure (so the caller can print a marker
// instead of crashing on a simulator / unsupported device).
func pwBenchMatchGPU(numDesc: Int, numPairs: Int) -> Double {
    let D = 128

    guard numDesc > 0, numPairs > 0,
          let device = MTLCreateSystemDefaultDevice(),
          let queue = device.makeCommandQueue() else {
        return -1.0
    }

    // Pipeline from the default .metallib (MatchKernel.metal is compiled into
    // the app bundle's default library by Xcode automatically).
    let pipeline: MTLComputePipelineState
    do {
        guard let library = device.makeDefaultLibrary(),
              let fn = library.makeFunction(name: "pw_match_kernel") else {
            return -1.0
        }
        pipeline = try device.makeComputePipelineState(function: fn)
    } catch {
        return -1.0
    }

    // Random, L2-normalized 128-d descriptors. Seeded deterministically so the
    // GPU workload mirrors the CPU kernel's fixed-seed data (NativeBench.cpp
    // uses mt19937(123)); the absolute values do not matter for timing, but a
    // fixed seed keeps runs comparable. A tiny xorshift64 RNG avoids any
    // SystemRandomNumberGenerator nondeterminism.
    var state: UInt64 = 123
    func nextUnitFloat() -> Float {
        state ^= state << 13
        state ^= state >> 7
        state ^= state << 17
        return Float(state >> 40) / Float(1 << 24)   // 24-bit mantissa in [0,1)
    }
    func makeDescriptors(_ n: Int) -> [Float] {
        var v = [Float](repeating: 0, count: n * D)
        for i in 0..<n {
            var s: Float = 0
            for d in 0..<D {
                let x = nextUnitFloat()
                v[i * D + d] = x
                s += x * x
            }
            let inv = 1.0 / (s.squareRoot() + 1e-9)
            for d in 0..<D { v[i * D + d] *= inv }
        }
        return v
    }
    let aHost = makeDescriptors(numDesc)
    let bHost = makeDescriptors(numDesc)

    let descBytes = numDesc * D * MemoryLayout<Float>.stride
    var nd = UInt32(numDesc)

    guard let aBuf = device.makeBuffer(bytes: aHost, length: descBytes, options: .storageModeShared),
          let bBuf = device.makeBuffer(bytes: bHost, length: descBytes, options: .storageModeShared),
          let outBuf = device.makeBuffer(length: numDesc * MemoryLayout<Int32>.stride,
                                         options: .storageModeShared) else {
        return -1.0
    }

    // Threadgroup sizing: one thread per query, 1-D grid.
    let tgWidth = min(pipeline.maxTotalThreadsPerThreadgroup, 256)
    let threadsPerThreadgroup = MTLSize(width: tgWidth, height: 1, depth: 1)
    let gridSize = MTLSize(width: numDesc, height: 1, depth: 1)

    let t0 = DispatchTime.now()
    for _ in 0..<numPairs {
        guard let cmd = queue.makeCommandBuffer(),
              let enc = cmd.makeComputeCommandEncoder() else {
            return -1.0
        }
        enc.setComputePipelineState(pipeline)
        enc.setBuffer(aBuf, offset: 0, index: 0)
        enc.setBuffer(bBuf, offset: 0, index: 1)
        enc.setBuffer(outBuf, offset: 0, index: 2)
        enc.setBytes(&nd, length: MemoryLayout<UInt32>.stride, index: 3)
        // dispatchThreads handles non-multiple grid sizes (the kernel also
        // guards gid >= numDesc) and requires non-uniform threadgroup support,
        // available on all A-series GPUs on iOS 17.
        enc.dispatchThreads(gridSize, threadsPerThreadgroup: threadsPerThreadgroup)
        enc.endEncoding()
        cmd.commit()
        cmd.waitUntilCompleted()   // GPU-synchronized: timer measures real GPU work
    }
    let elapsedNs = DispatchTime.now().uptimeNanoseconds - t0.uptimeNanoseconds
    return Double(elapsedNs) / 1_000_000.0
}
