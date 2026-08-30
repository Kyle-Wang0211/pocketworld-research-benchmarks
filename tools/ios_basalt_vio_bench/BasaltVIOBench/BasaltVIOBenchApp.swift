import SwiftUI

@main
struct BasaltVIOBenchApp: App {
    @StateObject private var model = BenchViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
        }
    }
}

