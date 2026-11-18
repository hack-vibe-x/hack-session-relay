#!/bin/zsh
# Session Relay 관리자 앱을 빌드해 ~/Applications 에 설치한다. 앱은 이 저장소의 admin/admin.py를 켜서 자기 창에 띄운다.
#   admin/mac/build.sh install     빌드·설치 (저장소를 옮겼으면 다시 실행)
#   admin/mac/build.sh uninstall   지우기
# 필요한 것: Xcode 명령행 도구(xcrun swiftc). 관리자 설정은 그대로 admin/config.json 을 쓴다.
ROOT=${0:A:h:h:h}
APP="$HOME/Applications/Session Relay.app"
ID=ai.hack-vibe-x.session-relay.admin

case $1 in
  install)
    pkill -f "$APP/Contents/MacOS/SessionRelay" 2>/dev/null
    rm -rf "$APP" && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" || exit 1
    xcrun swiftc -O -swift-version 5 -framework AppKit -framework WebKit -o "$APP/Contents/MacOS/SessionRelay" "$ROOT/admin/mac/App.swift" || exit 1
    TMP=$(mktemp -d)
    xcrun swiftc -O -swift-version 5 -framework AppKit -o "$TMP/make-icon" "$ROOT/admin/mac/MakeIcon.swift" || exit 1
    "$TMP/make-icon" "$TMP/AppIcon.iconset" "$ROOT/admin/mac/icon-1024.png" && iconutil -c icns -o "$APP/Contents/Resources/AppIcon.icns" "$TMP/AppIcon.iconset" || exit 1
    rm -rf "$TMP"
    cat > "$APP/Contents/Info.plist" <<INFO
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>$ID</string>
  <key>CFBundleName</key><string>Session Relay</string>
  <key>CFBundleDisplayName</key><string>Session Relay</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundleExecutable</key><string>SessionRelay</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>ProjectRoot</key><string>$ROOT</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
INFO
    codesign --force --sign - "$APP" 2>/dev/null
    touch "$APP" # Finder와 Dock이 새 아이콘을 읽게
    echo "설치했습니다: $APP"
    echo "Launchpad나 Spotlight에서 'Session Relay'로 열 수 있습니다."
    ;;
  uninstall)
    pkill -f "$APP/Contents/MacOS/SessionRelay" 2>/dev/null
    rm -rf "$APP" && echo "지웠습니다: $APP"
    ;;
  *)
    echo "사용법: $0 install | uninstall"
    exit 1
    ;;
esac
