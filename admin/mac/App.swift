// Session Relay 관리자 앱: 관리자 웹(admin/admin.py)을 브라우저 탭 없이 자기 창으로 띄운다.
// 켜질 때 http://127.0.0.1:8787 이 응답하지 않으면 admin.py를 직접 켜고, 앱을 끌 때 자기가 켠 것만 끈다.
// 설치: admin/mac/build.sh install
import AppKit
import WebKit

let port = 8787
let base = URL(string: "http://127.0.0.1:\(port)/")!
let root = Bundle.main.object(forInfoDictionaryKey: "ProjectRoot") as? String ?? ""
let logURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/session-relay-admin.log")

func isLocal(_ url: URL) -> Bool {
  (url.host == "127.0.0.1" || url.host == "localhost") && url.port == port && url.scheme == "http"
}

/** 관리자 웹이 응답하는지(/api/config가 JSON을 준다). */
func adminResponds(_ done: @escaping (Bool) -> Void) {
  var req = URLRequest(url: base.appendingPathComponent("api/config"), timeoutInterval: 1.5)
  req.cachePolicy = .reloadIgnoringLocalCacheData
  URLSession.shared.dataTask(with: req) { data, res, _ in
    let ok = (res as? HTTPURLResponse)?.statusCode == 200
      && (data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any])?["ready"] != nil
    DispatchQueue.main.async { done(ok) }
  }.resume()
}

func python() -> String {
  for p in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"] where FileManager.default.isExecutableFile(atPath: p) {
    return p
  }
  return "/usr/bin/python3"
}

final class App: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandler {
  var window: NSWindow!
  var webView: WKWebView!
  var server: Process? // 이 앱이 켠 admin.py(이미 켜져 있던 것은 건드리지 않는다)
  var downloads: [ObjectIdentifier: URL] = [:]
  var waited = 0
  var quitting = false

  func applicationDidFinishLaunching(_ n: Notification) {
    NSApp.mainMenu = mainMenu()
    build()
    webView.loadHTMLString(statusPage("관리자 화면을 켜는 중입니다", "잠시만 기다려 주세요.", spinner: true), baseURL: nil)
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)
    adminResponds { ok in
      if ok { self.open() } else { self.startServer() }
    }
  }

  func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

  func applicationWillTerminate(_ n: Notification) {
    quitting = true
    if let server, server.isRunning { server.terminate() }
  }

  // MARK: 관리자 웹 켜기

  func startServer() {
    let script = (root as NSString).appendingPathComponent("admin/admin.py")
    guard FileManager.default.fileExists(atPath: script) else {
      return fail("admin.py를 찾을 수 없습니다", "앱을 만든 뒤 저장소 폴더가 옮겨졌습니다. 저장소에서 admin/mac/build.sh install 을 다시 실행해 주세요.\n찾은 위치: \(script)")
    }
    FileManager.default.createFile(atPath: logURL.path, contents: nil)
    let log = try? FileHandle(forWritingTo: logURL)
    let p = Process()
    p.executableURL = URL(fileURLWithPath: python())
    p.arguments = ["-u", script]
    p.currentDirectoryURL = URL(fileURLWithPath: root)
    p.standardOutput = log
    p.standardError = log
    p.terminationHandler = { proc in
      DispatchQueue.main.async {
        guard self.server === proc, !self.quitting else { return }
        self.server = nil
        self.fail("관리자 화면이 꺼졌습니다", self.logTail())
      }
    }
    do { try p.run() } catch {
      return fail("관리자 화면을 켜지 못했습니다", error.localizedDescription)
    }
    server = p
    waited = 0
    waitForServer()
  }

  func waitForServer() {
    adminResponds { ok in
      if ok { return self.open() }
      self.waited += 1
      if self.waited > 60 { return self.fail("관리자 화면이 응답하지 않습니다", self.logTail()) } // 약 15초
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.waitForServer() }
    }
  }

  func open() { webView.load(URLRequest(url: base)) }

  func logTail() -> String {
    let text = (try? String(contentsOf: logURL, encoding: .utf8)) ?? ""
    let lines = text.split(separator: "\n", omittingEmptySubsequences: false).suffix(12).joined(separator: "\n")
    return lines.isEmpty ? "기록: \(logURL.path)" : lines + "\n\n기록: \(logURL.path)"
  }

  func fail(_ title: String, _ detail: String) {
    webView.loadHTMLString(statusPage(title, detail, spinner: false), baseURL: nil)
  }

  @objc func retry() {
    if let server, server.isRunning { open() } else {
      webView.loadHTMLString(statusPage("관리자 화면을 켜는 중입니다", "잠시만 기다려 주세요.", spinner: true), baseURL: nil)
      adminResponds { ok in if ok { self.open() } else { self.startServer() } }
    }
  }

  // MARK: 창

  func build() {
    let config = WKWebViewConfiguration()
    config.websiteDataStore = .default()
    // 화면의 "복사" 버튼: 웹 클립보드 대신 Mac 클립보드에 바로 넣는다(앱 창에서는 웹 클립보드 권한이 들쭉날쭉하다)
    config.userContentController.add(self, name: "clipboard")
    config.userContentController.addUserScript(WKUserScript(source: """
      if (navigator.clipboard) navigator.clipboard.writeText = t => { webkit.messageHandlers.clipboard.postMessage(String(t)); return Promise.resolve(); };
      """, injectionTime: .atDocumentStart, forMainFrameOnly: true))
    webView = WKWebView(frame: .zero, configuration: config)
    webView.navigationDelegate = self
    webView.uiDelegate = self
    webView.allowsMagnification = true
    window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
    window.title = "Session Relay"
    window.minSize = NSSize(width: 720, height: 520)
    window.contentView = webView
    window.isReleasedWhenClosed = false
    window.tabbingMode = .disallowed
    window.delegate = self
    window.center()
    window.setFrameAutosaveName("SessionRelayAdminWindow") // 크기와 위치를 기억한다
  }

  func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
    guard message.name == "clipboard", let text = message.body as? String else { return }
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
  }

  @objc func reload() { if webView.url.map(isLocal) == true { webView.reload() } else { retry() } }
  @objc func openInBrowser() { NSWorkspace.shared.open(webView.url.flatMap { isLocal($0) ? $0 : nil } ?? base) }
  @objc func openLog() { NSWorkspace.shared.open(logURL) }
  @objc func zoomIn() { webView.pageZoom = min(2, webView.pageZoom + 0.1) }
  @objc func zoomOut() { webView.pageZoom = max(0.5, webView.pageZoom - 0.1) }
  @objc func zoomReset() { webView.pageZoom = 1 }

  // MARK: 이동

  func webView(_ wv: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
    if action.shouldPerformDownload { return decisionHandler(.download) } // <a download> (기간 zip은 blob: 주소로 온다)
    guard let url = action.request.url, url.scheme == "http" || url.scheme == "https" else { return decisionHandler(.allow) }
    if !isLocal(url) { // 바깥 주소(GitHub 등)는 기본 브라우저로
      NSWorkspace.shared.open(url)
      return decisionHandler(.cancel)
    }
    decisionHandler(.allow)
  }

  func webView(_ wv: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
    let disposition = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition")?.lowercased() ?? ""
    decisionHandler(disposition.hasPrefix("attachment") || !response.canShowMIMEType ? .download : .allow)
  }

  func webView(_ wv: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
  func webView(_ wv: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

  func webView(_ wv: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError error: Error) {
    let e = error as NSError
    if e.code == NSURLErrorCancelled || (e.domain == "WebKitErrorDomain" && e.code == 102) { return }
    if let server, server.isRunning { // 켜져 있는데 닿지 않는다: 되풀이하지 않고 알린다
      fail("관리자 화면에 연결하지 못했습니다", e.localizedDescription + "\n\n" + logTail())
    } else {
      retry() // 꺼져 있으면 다시 켠다
    }
  }

  func webViewWebContentProcessDidTerminate(_ wv: WKWebView) { wv.reload() }

  // MARK: 내려받기: 다운로드 폴더에 저장하고 Finder에서 보여 준다

  func download(_ d: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
    let dir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
    let name = (suggestedFilename as NSString).lastPathComponent
    let stem = (name as NSString).deletingPathExtension, ext = (name as NSString).pathExtension
    var url = dir.appendingPathComponent(name)
    var i = 1
    while FileManager.default.fileExists(atPath: url.path) {
      url = dir.appendingPathComponent(ext.isEmpty ? "\(stem) (\(i))" : "\(stem) (\(i)).\(ext)")
      i += 1
    }
    downloads[ObjectIdentifier(d)] = url
    completionHandler(url)
  }

  func downloadDidFinish(_ d: WKDownload) {
    if let url = downloads.removeValue(forKey: ObjectIdentifier(d)) { NSWorkspace.shared.activateFileViewerSelecting([url]) }
  }

  func download(_ d: WKDownload, didFailWithError error: Error, resumeData: Data?) {
    downloads.removeValue(forKey: ObjectIdentifier(d))
    let a = NSAlert()
    a.messageText = "내려받지 못했습니다"
    a.informativeText = error.localizedDescription
    a.beginSheetModal(for: window)
  }

  // MARK: 웹 화면의 알림·확인 창, 새 창

  func webView(_ wv: WKWebView, runJavaScriptAlertPanelWithMessage text: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
    let a = NSAlert()
    a.messageText = text
    a.addButton(withTitle: "확인")
    a.beginSheetModal(for: window) { _ in completionHandler() }
  }

  func webView(_ wv: WKWebView, runJavaScriptConfirmPanelWithMessage text: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
    let a = NSAlert()
    let parts = text.components(separatedBy: "\n")
    a.messageText = parts.first ?? text
    a.informativeText = parts.dropFirst().joined(separator: "\n")
    a.addButton(withTitle: "확인")
    a.addButton(withTitle: "취소")
    a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
  }

  func webView(_ wv: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
    let a = NSAlert()
    a.messageText = prompt
    let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
    field.stringValue = defaultText ?? ""
    a.accessoryView = field
    a.addButton(withTitle: "확인")
    a.addButton(withTitle: "취소")
    a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
  }

  /** target=_blank 링크와 window.open: 바깥 주소는 브라우저로, 관리자 주소는 이 창에서. */
  func webView(_ wv: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
    if let url = action.request.url {
      if isLocal(url) { wv.load(action.request) } else { NSWorkspace.shared.open(url) }
    }
    return nil
  }

  // MARK: 메뉴

  func mainMenu() -> NSMenu {
    let bar = NSMenu()
    func menu(_ title: String, _ items: [NSMenuItem]) {
      let m = NSMenu(title: title)
      items.forEach(m.addItem)
      let top = NSMenuItem(title: title, action: nil, keyEquivalent: "")
      top.submenu = m
      bar.addItem(top)
    }
    func item(_ title: String, _ action: Selector?, _ key: String = "", _ mods: NSEvent.ModifierFlags = .command, target: AnyObject? = nil) -> NSMenuItem {
      let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
      i.keyEquivalentModifierMask = mods
      i.target = target
      return i
    }
    menu("Session Relay", [
      item("Session Relay 정보", #selector(NSApplication.orderFrontStandardAboutPanel(_:))),
      .separator(),
      item("Session Relay 가리기", #selector(NSApplication.hide(_:)), "h"),
      item("기타 가리기", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
      .separator(),
      item("Session Relay 종료", #selector(NSApplication.terminate(_:)), "q"),
    ])
    menu("편집", [
      item("실행 취소", Selector(("undo:")), "z"),
      item("실행 복귀", Selector(("redo:")), "z", [.command, .shift]),
      .separator(),
      item("오려두기", #selector(NSText.cut(_:)), "x"),
      item("복사하기", #selector(NSText.copy(_:)), "c"),
      item("붙여넣기", #selector(NSText.paste(_:)), "v"),
      item("전체 선택", #selector(NSText.selectAll(_:)), "a"),
    ])
    menu("보기", [
      item("새로 고침", #selector(reload), "r", target: self),
      .separator(),
      item("확대", #selector(zoomIn), "+", target: self),
      item("축소", #selector(zoomOut), "-", target: self),
      item("실제 크기", #selector(zoomReset), "0", target: self),
      .separator(),
      item("브라우저에서 열기", #selector(openInBrowser), "o", [.command, .shift], target: self),
      item("관리자 웹 기록 보기", #selector(openLog), target: self),
    ])
    menu("윈도우", [
      item("최소화", #selector(NSWindow.performMiniaturize(_:)), "m"),
      item("닫기", #selector(NSWindow.performClose(_:)), "w"),
    ])
    return bar
  }
}

func statusPage(_ title: String, _ detail: String, spinner: Bool) -> String {
  func esc(_ s: String) -> String {
    s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
  }
  return """
  <!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="color-scheme" content="light dark">
  <style>
    body { margin: 0; height: 100vh; display: grid; place-items: center; font: 15px -apple-system, "Apple SD Gothic Neo", sans-serif; background: #f6f7f9; color: #16181d; }
    @media (prefers-color-scheme: dark) { body { background: #111318; color: #eceef2; } pre { background: #1a1d24 !important; color: #c4cad6 !important; } }
    main { max-width: 640px; padding: 24px; text-align: center; }
    h1 { font-size: 19px; margin: 0 0 10px; }
    pre { text-align: left; white-space: pre-wrap; word-break: break-all; font: 12px ui-monospace, Menlo, monospace; background: #eceef2; color: #3a4150; padding: 12px; border-radius: 8px; margin: 0 0 18px; }
    p { color: #667085; margin: 0; }
    button { font: inherit; padding: 8px 16px; border-radius: 8px; border: 0; background: #ff5a1f; color: #fff; cursor: pointer; }
    .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #ff5a1f; margin-right: 8px; animation: b .8s infinite alternate; }
    @keyframes b { from { opacity: .2 } to { opacity: 1 } }
  </style></head><body><main>
    <h1>\(spinner ? "<span class=\"dot\"></span>" : "")\(esc(title))</h1>
    \(spinner ? "<p>\(esc(detail))</p>" : "<pre>\(esc(detail))</pre><button onclick=\"location.href='\(base.absoluteString)'\">다시 시도</button>")
  </main></body></html>
  """
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
