// Session Relay 앱 아이콘: Hack Work Studio와 같은 틀(흰 바탕, hack-vibe-x X 기호, 아래 검정 띠)에 띠 글자만 "relay".
// X 기호는 hack-vibe-x.ai의 hack-vibe-x-symbol-light.svg 경로를 그대로 옮겼다.
// 사용: swift MakeIcon.swift <iconset 폴더> [1024 PNG 경로]   (admin/mac/build.sh가 부른다)
import AppKit

let ink = "M47.97 604.94 C31.09 602.46 15.54 591.88 8.59 578.18 C-4.18 552.98 5.21 516.03 31.23 489.15 C45.13 474.79 55.62 467.42 94 445.05 C133.14 422.24 147.16 412.55 176.33 388.15 C195.3 372.29 210.74 358.27 229.24 340.12 C237.35 332.16 244.15 325.84 244.35 326.08 C247.14 329.29 270.42 359.56 283.36 376.79 L300.09 399.08 L296.8 402.85 C281.87 419.96 267.13 437.42 248.54 460 C220.6 493.92 209.31 506.55 190.99 524.34 C159.03 555.4 124.58 582.19 102.16 593.43 C91.69 598.69 75.89 603.72 66.03 604.95 C56.66 606.11 55.91 606.11 47.97 604.94 Z M376.82 293.28 C360.09 272.21 328 226.66 328 223.97 C328 221.84 363.83 165.67 381.25 140.5 C425.13 77.08 454.62 44.16 483.74 26.1 C500.68 15.6 520.83 7.63 538.5 4.46 C550.26 2.34 569.55 2.35 577.5 4.48 C606.26 12.15 620.71 34.47 614.89 62.2 C610.96 80.9 594.48 102.37 575.11 114 C553.64 126.89 548.36 130.35 535.75 139.74 C487 176.06 454.72 209.92 408.13 273.61 C398.12 287.3 388.9 299.75 387.65 301.28 L385.38 304.05 L376.82 293.28 Z"
let accent = "M545.5 590.86 C527.21 588.85 501.32 580.64 480.5 570.26 C437.7 548.93 402.17 517.82 360.88 465.5 C349.85 451.53 328.19 423.15 316.98 408 C282.67 361.6 257.14 328.54 227.01 291.5 C216.27 278.3 204.92 264.12 201.78 260 C168.56 216.35 161.69 207.98 147.02 193.24 C133.84 180.02 121.25 169.68 104.02 157.98 C78.97 140.95 69.29 127.12 68.24 106.87 C67.64 95.25 68.91 89.07 73.87 79.5 C80.76 66.22 93.34 56.74 110 52.28 C118.09 50.12 138.45 49.91 148.5 51.89 C178.7 57.83 209 75.21 232.29 99.97 C246.25 114.8 253.51 125.03 284.54 173.5 C347.49 271.84 368.88 300.51 416.62 350.5 C457.74 393.56 486.37 418.48 515.2 436.32 C525.66 442.79 550.99 454.84 565 460.01 C580.62 465.77 593.04 471.66 602 477.57 C640.54 502.95 649.45 543.39 622.5 570.56 C605.81 587.38 578.75 594.52 545.5 590.86 Z"

func color(_ hex: UInt32) -> NSColor {
  NSColor(srgbRed: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255, blue: CGFloat(hex & 0xff) / 255, alpha: 1)
}

/** SVG 경로(절대 좌표 M, L, C, Z만)를 NSBezierPath로. y는 위에서 아래로 그대로 두고, 그릴 때 뒤집는다. */
func path(_ d: String) -> NSBezierPath {
  let p = NSBezierPath()
  var nums: [CGFloat] = []
  var cmd: Character = " "
  func flush() {
    switch cmd {
    case "M": p.move(to: NSPoint(x: nums[0], y: nums[1]))
    case "L": p.line(to: NSPoint(x: nums[0], y: nums[1]))
    case "C": p.curve(to: NSPoint(x: nums[4], y: nums[5]), controlPoint1: NSPoint(x: nums[0], y: nums[1]), controlPoint2: NSPoint(x: nums[2], y: nums[3]))
    case "Z": p.close()
    default: break
    }
    nums = []
  }
  for var token in d.split(separator: " ") { // 명령 글자는 첫 숫자에 붙어 있다: "M47.97"
    if let c = token.first, c.isLetter {
      flush()
      cmd = c
      token = token.dropFirst()
    }
    if let v = Double(token) { nums.append(CGFloat(v)) }
  }
  flush()
  p.windingRule = .evenOdd
  return p
}

func draw(_ px: Int) -> Data {
  let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
  NSGraphicsContext.saveGraphicsState()
  NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
  let ctx = NSGraphicsContext.current!.cgContext
  ctx.scaleBy(x: CGFloat(px) / 1024, y: CGFloat(px) / 1024)
  // 1024 칸, 위에서 아래로 재는 좌표(SVG, Hack Work Studio 아이콘과 같은 방향)
  ctx.translateBy(x: 0, y: 1024)
  ctx.scaleBy(x: 1, y: -1)

  NSColor.white.setFill()
  NSRect(x: 0, y: 0, width: 1024, height: 1024).fill()

  // X 기호: Hack Work Studio 아이콘과 같은 자리(가로 268~757, 세로 180~645)
  let black = path(ink), orange = path(accent)
  let bounds = black.bounds.union(orange.bounds)
  let target = NSRect(x: 268, y: 180, width: 489, height: 465)
  let k = min(target.width / bounds.width, target.height / bounds.height)
  var t = AffineTransform(translationByX: target.midX - bounds.midX * k, byY: target.midY - bounds.midY * k)
  t.scale(k)
  black.transform(using: t)
  orange.transform(using: t)
  color(0x000000).setFill()
  black.fill()
  color(0xFF5A1F).setFill()
  orange.fill()

  // 아래 띠: 위는 곧고 아래 두 모서리만 둥글다
  let band = NSRect(x: 100, y: 700, width: 824, height: 222)
  let r: CGFloat = 186
  let shape = NSBezierPath()
  shape.move(to: NSPoint(x: band.minX, y: band.minY))
  shape.line(to: NSPoint(x: band.maxX, y: band.minY))
  shape.line(to: NSPoint(x: band.maxX, y: band.maxY - r))
  shape.appendArc(withCenter: NSPoint(x: band.maxX - r, y: band.maxY - r), radius: r, startAngle: 0, endAngle: 90)
  shape.line(to: NSPoint(x: band.minX + r, y: band.maxY))
  shape.appendArc(withCenter: NSPoint(x: band.minX + r, y: band.maxY - r), radius: r, startAngle: 90, endAngle: 180)
  shape.close()
  NSColor.black.setFill()
  shape.fill()

  // 띠 글자: 뒤집힌 좌표에서 글자가 거꾸로 서지 않게 이 부분만 다시 뒤집는다
  let font = NSFont.systemFont(ofSize: 152, weight: .bold)
  let text = NSAttributedString(string: "relay", attributes: [.font: font, .foregroundColor: NSColor.white])
  let size = text.size()
  // "studio"보다 조금 위: "y"의 꼬리까지 넣어 띠 가운데에 오게
  let baseline: CGFloat = 850
  ctx.saveGState()
  ctx.translateBy(x: 0, y: baseline)
  ctx.scaleBy(x: 1, y: -1)
  text.draw(at: NSPoint(x: 512 - size.width / 2, y: font.descender)) // 그리는 점은 글줄의 아래 끝(바닥선 - 내림)
  ctx.restoreGState()

  NSGraphicsContext.restoreGraphicsState()
  return rep.representation(using: .png, properties: [:])!
}

let out = URL(fileURLWithPath: CommandLine.arguments[1])
try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
for (pt, scale) in [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2)] {
  let name = scale == 1 ? "icon_\(pt)x\(pt).png" : "icon_\(pt)x\(pt)@2x.png"
  try! draw(pt * scale).write(to: out.appendingPathComponent(name))
}
if CommandLine.arguments.count > 2 { try! draw(1024).write(to: URL(fileURLWithPath: CommandLine.arguments[2])) }
