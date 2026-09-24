import Accelerate
import CoreML
import Foundation

enum RunnerError: Error, CustomStringConvertible {
  case missingArgument(String)
  case invalidArgument(String)
  case io(String)
  case model(String)

  var description: String {
    switch self {
    case .missingArgument(let value): return "missing argument: \(value)"
    case .invalidArgument(let value): return "invalid argument: \(value)"
    case .io(let value): return "io error: \(value)"
    case .model(let value): return "model error: \(value)"
    }
  }
}

struct Config {
  let modelPath: String
  let tensorDir: String
  let outputDir: String
  let runName: String
  let frameCount: Int
  let height: Int
  let width: Int

  static func parse(_ args: [String]) throws -> Config {
    var values: [String: String] = [:]
    var i = 1
    while i < args.count {
      let key = args[i]
      guard key.hasPrefix("--") else {
        throw RunnerError.invalidArgument("unexpected token \(key)")
      }
      guard i + 1 < args.count else {
        throw RunnerError.missingArgument(key)
      }
      values[String(key.dropFirst(2))] = args[i + 1]
      i += 2
    }
    func required(_ key: String) throws -> String {
      guard let value = values[key], !value.isEmpty else {
        throw RunnerError.missingArgument("--\(key)")
      }
      return value
    }
    func intValue(_ key: String) throws -> Int {
      let raw = try required(key)
      guard let value = Int(raw), value > 0 else {
        throw RunnerError.invalidArgument("--\(key) must be positive Int, got \(raw)")
      }
      return value
    }
    return Config(
      modelPath: try required("model"),
      tensorDir: try required("tensor-dir"),
      outputDir: try required("out"),
      runName: try required("name"),
      frameCount: try intValue("frames"),
      height: try intValue("height"),
      width: try intValue("width")
    )
  }
}

final class ImageOnlyInput: MLFeatureProvider {
  let image: MLMultiArray
  var featureNames: Set<String> { ["image"] }

  init(image: MLMultiArray) {
    self.image = image
  }

  func featureValue(for featureName: String) -> MLFeatureValue? {
    featureName == "image" ? MLFeatureValue(multiArray: image) : nil
  }
}

func descriptor(_ array: MLMultiArray) -> [String: Any] {
  [
    "count": array.count,
    "dataTypeRaw": array.dataType.rawValue,
    "shape": array.shape.map { $0.intValue },
    "strides": array.strides.map { $0.intValue },
  ]
}

func compactRowMajorStrides(_ shape: [Int]) -> [Int] {
  guard !shape.isEmpty else { return [] }
  var strides = [Int](repeating: 1, count: shape.count)
  if shape.count >= 2 {
    for i in stride(from: shape.count - 2, through: 0, by: -1) {
      strides[i] = strides[i + 1] * max(1, shape[i + 1])
    }
  }
  return strides
}

func copyStridedFloatArray(
  shape: [Int],
  strides: [Int],
  compactStrides: [Int],
  out: inout [Float],
  read: (Int) -> Float
) {
  guard !shape.isEmpty else { return }
  func walk(_ dim: Int, _ logicalOffset: Int, _ storageOffset: Int) {
    if dim == shape.count {
      out[logicalOffset] = read(storageOffset)
      return
    }
    let n = shape[dim]
    let logicalStep = compactStrides[dim]
    let storageStep = strides[dim]
    for i in 0..<n {
      walk(
        dim + 1,
        logicalOffset + i * logicalStep,
        storageOffset + i * storageStep
      )
    }
  }
  walk(0, 0, 0)
}

func multiArrayToFloatBuffer(_ array: MLMultiArray) throws -> [Float] {
  let shape = array.shape.map { $0.intValue }
  let strides = array.strides.map { $0.intValue }
  let compact = compactRowMajorStrides(shape)
  let count = shape.reduce(1) { $0 * max(0, $1) }
  guard count == array.count else {
    throw RunnerError.model("logical count mismatch shape=\(shape) count=\(array.count)")
  }

  var out = [Float](repeating: 0, count: count)
  if strides == compact {
    switch array.dataType {
    case .float32:
      let ptr = array.dataPointer.bindMemory(to: Float32.self, capacity: count)
      for i in 0..<count { out[i] = ptr[i] }
    case .float16:
      let ptr = array.dataPointer.bindMemory(to: Float16.self, capacity: count)
      for i in 0..<count { out[i] = Float(ptr[i]) }
    case .double:
      let ptr = array.dataPointer.bindMemory(to: Double.self, capacity: count)
      for i in 0..<count { out[i] = Float(ptr[i]) }
    default:
      throw RunnerError.model("unsupported MLMultiArray dtype raw=\(array.dataType.rawValue)")
    }
    return out
  }

  switch array.dataType {
  case .float32:
    let ptr = array.dataPointer.bindMemory(
      to: Float32.self,
      capacity: storageElementCapacity(shape: shape, strides: strides)
    )
    copyStridedFloatArray(shape: shape, strides: strides, compactStrides: compact, out: &out) {
      ptr[$0]
    }
  case .float16:
    let ptr = array.dataPointer.bindMemory(
      to: Float16.self,
      capacity: storageElementCapacity(shape: shape, strides: strides)
    )
    copyStridedFloatArray(shape: shape, strides: strides, compactStrides: compact, out: &out) {
      Float(ptr[$0])
    }
  case .double:
    let ptr = array.dataPointer.bindMemory(
      to: Double.self,
      capacity: storageElementCapacity(shape: shape, strides: strides)
    )
    copyStridedFloatArray(shape: shape, strides: strides, compactStrides: compact, out: &out) {
      Float(ptr[$0])
    }
  default:
    throw RunnerError.model("unsupported MLMultiArray dtype raw=\(array.dataType.rawValue)")
  }
  return out
}

func storageElementCapacity(shape: [Int], strides: [Int]) -> Int {
  guard shape.count == strides.count else { return 0 }
  var maxOffset = 0
  for i in 0..<shape.count {
    maxOffset += max(0, shape[i] - 1) * strides[i]
  }
  return maxOffset + 1
}

func writeFloats(_ values: ArraySlice<Float>, to url: URL) throws {
  var copy = Array(values)
  let data = copy.withUnsafeMutableBufferPointer { Data(buffer: $0) }
  try data.write(to: url, options: .atomic)
}

func writeFloats(_ values: [Float], to url: URL) throws {
  var copy = values
  let data = copy.withUnsafeMutableBufferPointer { Data(buffer: $0) }
  try data.write(to: url, options: .atomic)
}

func writeJSON(_ value: Any, to url: URL) throws {
  let data = try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
  try data.write(to: url, options: .atomic)
}

func makeImageArray(config: Config) throws -> MLMultiArray {
  let array = try MLMultiArray(
    shape: [
      NSNumber(value: 1),
      NSNumber(value: config.frameCount),
      NSNumber(value: 3),
      NSNumber(value: config.height),
      NSNumber(value: config.width),
    ],
    dataType: .float32
  )
  let ptr = array.dataPointer.bindMemory(to: Float32.self, capacity: array.count)
  let perViewFloats = 3 * config.height * config.width
  let expectedBytes = perViewFloats * MemoryLayout<Float32>.stride
  let tensorRoot = URL(fileURLWithPath: config.tensorDir)
  for frameIndex in 0..<config.frameCount {
    let name = String(format: "real_%03d.float32_chw.bin", frameIndex)
    let url = tensorRoot.appendingPathComponent(name)
    let data = try Data(contentsOf: url)
    guard data.count == expectedBytes else {
      throw RunnerError.io("\(url.path) expected \(expectedBytes) bytes, got \(data.count)")
    }
    try data.withUnsafeBytes { raw in
      guard let src = raw.bindMemory(to: Float32.self).baseAddress else {
        throw RunnerError.io("empty tensor \(url.path)")
      }
      ptr.advanced(by: frameIndex * perViewFloats).update(from: src, count: perViewFloats)
    }
  }
  return array
}

func main() throws {
  let config = try Config.parse(CommandLine.arguments)
  let start = Date()
  let outputRoot = URL(fileURLWithPath: config.outputDir)
  let depthDir = outputRoot.appendingPathComponent("relative_depth", isDirectory: true)
  let confDir = outputRoot.appendingPathComponent("confidence", isDirectory: true)
  let poseDir = outputRoot.appendingPathComponent("pred_pose", isDirectory: true)
  try FileManager.default.createDirectory(at: depthDir, withIntermediateDirectories: true)
  try FileManager.default.createDirectory(at: confDir, withIntermediateDirectories: true)
  try FileManager.default.createDirectory(at: poseDir, withIntermediateDirectories: true)

  let imageArray = try makeImageArray(config: config)
  let modelConfig = MLModelConfiguration()
  modelConfig.computeUnits = .cpuOnly
  let model = try MLModel(contentsOf: URL(fileURLWithPath: config.modelPath), configuration: modelConfig)
  let predictionStart = Date()
  let prediction = try model.prediction(from: ImageOnlyInput(image: imageArray))
  let predictionSeconds = Date().timeIntervalSince(predictionStart)

  guard let depthArray = prediction.featureValue(for: "depth")?.multiArrayValue,
        let confArray = prediction.featureValue(for: "depth_conf")?.multiArrayValue,
        let extrArray = prediction.featureValue(for: "pred_extrinsics")?.multiArrayValue,
        let intrArray = prediction.featureValue(for: "pred_intrinsics")?.multiArrayValue else {
    throw RunnerError.model("missing expected output features: \(prediction.featureNames)")
  }

  let depth = try multiArrayToFloatBuffer(depthArray)
  let conf = try multiArrayToFloatBuffer(confArray).map { $0 - 1.0 }
  let extr = try multiArrayToFloatBuffer(extrArray)
  let intr = try multiArrayToFloatBuffer(intrArray)
  let perFramePixels = config.height * config.width

  guard depth.count >= config.frameCount * perFramePixels,
        conf.count >= config.frameCount * perFramePixels,
        extr.count >= config.frameCount * 12,
        intr.count >= config.frameCount * 9 else {
    throw RunnerError.model("output size mismatch")
  }

  var frames: [[String: Any]] = []
  for frameIndex in 0..<config.frameCount {
    let safeID = String(
      format: "%@_window_000_%d_%d_real_%03d",
      config.runName,
      frameIndex,
      frameIndex,
      frameIndex
    )
    let depthPath = "relative_depth/\(safeID).bin"
    let confPath = "confidence/\(safeID).bin"
    let extrPath = "pred_pose/\(safeID)_extrinsics.bin"
    let intrPath = "pred_pose/\(safeID)_intrinsics.bin"

    let pixelLo = frameIndex * perFramePixels
    let pixelHi = pixelLo + perFramePixels
    try writeFloats(depth[pixelLo..<pixelHi], to: outputRoot.appendingPathComponent(depthPath))
    try writeFloats(conf[pixelLo..<pixelHi], to: outputRoot.appendingPathComponent(confPath))

    let extrLo = frameIndex * 12
    try writeFloats(extr[extrLo..<(extrLo + 12)], to: outputRoot.appendingPathComponent(extrPath))
    let intrLo = frameIndex * 9
    try writeFloats(intr[intrLo..<(intrLo + 9)], to: outputRoot.appendingPathComponent(intrPath))

    frames.append([
      "frameIndex": frameIndex,
      "frameID": String(format: "real_%03d", frameIndex),
      "relativeDepthPath": depthPath,
      "confidencePath": confPath,
      "predExtrinsicsPath": extrPath,
      "predIntrinsicsPath": intrPath,
      "depthWidth": config.width,
      "depthHeight": config.height,
    ])
  }

  let report: [String: Any] = [
    "schemaVersion": "aether_da3_coreml_stage1_mac_stride_correct_v1",
    "runName": config.runName,
    "frameCount": config.frameCount,
    "height": config.height,
    "width": config.width,
    "computeUnits": "cpuOnly",
    "elapsedSeconds": Date().timeIntervalSince(start),
    "predictionSeconds": predictionSeconds,
    "modelPath": config.modelPath,
    "tensorDir": config.tensorDir,
    "outputDir": config.outputDir,
    "outputDescriptors": [
      "depth": descriptor(depthArray),
      "depth_conf": descriptor(confArray),
      "pred_extrinsics": descriptor(extrArray),
      "pred_intrinsics": descriptor(intrArray),
    ],
    "frames": frames,
  ]
  try writeJSON(report, to: outputRoot.appendingPathComponent("stage1_coreml_report.json"))
  print("wrote \(outputRoot.path)")
  print("predictionSeconds=\(predictionSeconds)")
}

do {
  try main()
} catch {
  fputs("\(error)\n", stderr)
  exit(1)
}
