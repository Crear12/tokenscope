import AppKit
import Foundation

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let dashboardURL = URL(string: "http://127.0.0.1:8765/")!
    private var window: NSWindow!
    private var statusLabel: NSTextField!
    private var openButton: NSButton!
    private var server = Process()
    private var serverLog: FileHandle?
    private var configURL: URL!
    private var isStopping = false
    private var didOpenDashboard = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        makeWindow()
        do {
            try startServer()
            statusLabel.stringValue = "Starting the local dashboard…"
            Timer.scheduledTimer(withTimeInterval: 0.8, repeats: true) { [weak self] timer in
                guard let self else {
                    timer.invalidate()
                    return
                }
                self.checkServer(timer: timer)
            }
        } catch {
            statusLabel.stringValue = "TokenScope could not start."
            showError(error.localizedDescription)
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard server.isRunning else { return .terminateNow }
        if isStopping { return .terminateLater }
        isStopping = true
        statusLabel.stringValue = "Stopping dashboard and active collection…"
        openButton.isEnabled = false
        server.terminationHandler = { [weak sender] _ in
            DispatchQueue.main.async {
                sender?.reply(toApplicationShouldTerminate: true)
            }
        }
        server.interrupt() // SIGINT lets Python stop its HTTP server and collector cleanly.
        DispatchQueue.main.asyncAfter(deadline: .now() + 8) { [weak self] in
            guard let self, self.server.isRunning else { return }
            self.server.terminate()
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                if self.server.isRunning { self.server.interrupt() }
            }
        }
        return .terminateLater
    }

    private func makeWindow() {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 540, height: 270),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "TokenScope"
        window.center()
        window.delegate = self

        let content = window.contentView!
        let title = NSTextField(labelWithString: "TokenScope")
        title.font = .boldSystemFont(ofSize: 25)
        title.frame = NSRect(x: 34, y: 205, width: 470, height: 32)
        content.addSubview(title)

        statusLabel = NSTextField(wrappingLabelWithString: "Preparing TokenScope…")
        statusLabel.frame = NSRect(x: 36, y: 158, width: 466, height: 34)
        content.addSubview(statusLabel)

        let address = NSTextField(labelWithString: "http://127.0.0.1:8765/")
        address.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        address.frame = NSRect(x: 36, y: 132, width: 466, height: 20)
        content.addSubview(address)

        openButton = NSButton(title: "Open dashboard", target: self, action: #selector(openDashboard))
        openButton.frame = NSRect(x: 34, y: 82, width: 145, height: 34)
        openButton.bezelStyle = .rounded
        openButton.isEnabled = false
        content.addSubview(openButton)

        let settingsButton = NSButton(title: "Machine settings…", target: self, action: #selector(openSettings))
        settingsButton.frame = NSRect(x: 190, y: 82, width: 155, height: 34)
        settingsButton.bezelStyle = .rounded
        content.addSubview(settingsButton)

        let stopButton = NSButton(title: "Stop and quit", target: self, action: #selector(stopAndQuit))
        stopButton.frame = NSRect(x: 356, y: 82, width: 145, height: 34)
        stopButton.bezelStyle = .rounded
        content.addSubview(stopButton)

        let note = NSTextField(wrappingLabelWithString: "Machine settings and refresh cache stay in ~/Library/Application Support/TokenScope, outside this app.")
        note.font = .systemFont(ofSize: 11)
        note.textColor = .secondaryLabelColor
        note.frame = NSRect(x: 36, y: 31, width: 466, height: 40)
        content.addSubview(note)
    }

    private func startServer() throws {
        let fileManager = FileManager.default
        let support = fileManager.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/TokenScope", isDirectory: true)
        try fileManager.createDirectory(at: support, withIntermediateDirectories: true)
        configURL = support.appendingPathComponent("config.ini")
        if !fileManager.fileExists(atPath: configURL.path) {
            guard let template = Bundle.main.resourceURL?.appendingPathComponent("config.example.ini"),
                  fileManager.fileExists(atPath: template.path) else {
                throw LauncherError.missingConfigTemplate
            }
            try fileManager.copyItem(at: template, to: configURL)
        }

        let serverExecutable = Bundle.main.resourceURL!
            .appendingPathComponent("TokenScopeServer/TokenScopeServer")
        guard fileManager.isExecutableFile(atPath: serverExecutable.path) else {
            throw LauncherError.missingServer
        }

        let logURL = support.appendingPathComponent("server.log")
        if !fileManager.fileExists(atPath: logURL.path) {
            fileManager.createFile(atPath: logURL.path, contents: nil)
        }
        serverLog = try FileHandle(forWritingTo: logURL)
        try serverLog?.seekToEnd()
        server.executableURL = serverExecutable
        server.arguments = ["--host", "0.0.0.0", "--port", "8765", "--config", configURL.path]
        server.currentDirectoryURL = support
        server.standardOutput = serverLog
        server.standardError = serverLog
        server.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self, !self.isStopping else { return }
                self.statusLabel.stringValue = "The dashboard process stopped."
                self.showError("TokenScope exited with code \(process.terminationStatus). Its log is at:\n\(logURL.path)")
            }
        }
        try server.run()
    }

    private func checkServer(timer: Timer) {
        guard server.isRunning else {
            timer.invalidate()
            return
        }
        var request = URLRequest(url: dashboardURL.appendingPathComponent("api/status"))
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            guard let self else { return }
            DispatchQueue.main.async {
                guard self.server.isRunning else {
                    timer.invalidate()
                    return
                }
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { return }
                timer.invalidate()
                self.statusLabel.stringValue = "Running. Close this window to stop TokenScope."
                self.openButton.isEnabled = true
                if !self.didOpenDashboard {
                    self.didOpenDashboard = true
                    NSWorkspace.shared.open(self.dashboardURL)
                }
            }
        }.resume()
    }

    @objc private func openDashboard() {
        NSWorkspace.shared.open(dashboardURL)
    }

    @objc private func openSettings() {
        guard let configURL else { return }
        NSWorkspace.shared.open(configURL)
    }

    @objc private func stopAndQuit() {
        NSApp.terminate(nil)
    }

    private func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "TokenScope could not start"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}

private enum LauncherError: LocalizedError {
    case missingConfigTemplate
    case missingServer

    var errorDescription: String? {
        switch self {
        case .missingConfigTemplate:
            return "The bundled example configuration is missing."
        case .missingServer:
            return "The bundled TokenScope server is missing. Re-download the app bundle."
        }
    }
}
