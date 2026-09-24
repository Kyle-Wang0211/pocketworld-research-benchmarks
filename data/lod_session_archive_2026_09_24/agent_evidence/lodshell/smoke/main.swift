// SMOKE-ONLY entry: references the shell types so the link must resolve all of them, and
// compiles the exact registration line proposed for arloopbench's AppDelegate
// (didInitializeImplicitFlutterEngine).
import Flutter
func proposedBenchRegistration(_ engineBridge: FlutterImplicitEngineBridge) {
  GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
  if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "PwLodTexturePlugin") {
    PwLodTexturePlugin.register(with: registrar)
  } else {
    NSLog("[AppDelegate] registrar(forPlugin: PwLodTexturePlugin) nil — LOD page unavailable")
  }
}
let pluginType: FlutterPlugin.Type = PwLodTexturePlugin.self
print(pluginType, PwLodTexturePlugin.launchArgs(), PwLodProbe.toMap(PwLodProbe.sample()))
