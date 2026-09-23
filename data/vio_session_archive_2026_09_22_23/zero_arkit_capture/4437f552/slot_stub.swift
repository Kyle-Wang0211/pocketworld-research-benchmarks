// 仅用于类型检查:复刻 PwCameraSlot.swift 里那两个 @_cdecl 的**签名**。
import Foundation
public func pw_camera_slot_start(_ width: Int32, _ height: Int32,
                                 _ fps: Double,
                                 _ lensPosition: Double) -> Int32 { return 0 }
public func pw_camera_slot_stop() {}
