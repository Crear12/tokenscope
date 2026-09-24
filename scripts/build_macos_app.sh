#!/bin/bash
set -euo pipefail

VERSION="${VERSION:-}"
ARCH="${ARCH:-}"
if [[ ! "$VERSION" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "VERSION must be a semantic version such as v0.1.0" >&2
  exit 2
fi
if [[ "$ARCH" != arm64 && "$ARCH" != x86_64 ]]; then
  echo "ARCH must be arm64 or x86_64" >&2
  exit 2
fi
RELEASE_VERSION="${VERSION#v}"
BUILD_ROOT="build/macos-$ARCH"
DIST_DIR="$BUILD_ROOT/dist"
APP_DIR="$BUILD_ROOT/TokenScope.app"
APP_CONTENTS="$APP_DIR/Contents"

python -m PyInstaller \
  --noconfirm --clean --onedir --name TokenScopeServer \
  --distpath "$DIST_DIR" --workpath "$BUILD_ROOT/work" --specpath "$BUILD_ROOT" \
  --hidden-import update --hidden-import collect \
  --add-data "app.py:." --add-data "update.py:." --add-data "collect.py:." \
  --add-data "config.example.ini:." --add-data "web.html:." \
  --add-data "web.js:." --add-data "session_usage.js:." \
  --add-data "i18n.js:." --add-data "web.css:." \
  app.py

mkdir -p "$APP_CONTENTS/MacOS" "$APP_CONTENTS/Resources"
cp macos/Info.plist "$APP_CONTENTS/Info.plist"
cp -R "$DIST_DIR/TokenScopeServer" "$APP_CONTENTS/Resources/TokenScopeServer"
cp config.example.ini "$APP_CONTENTS/Resources/config.example.ini"
swiftc -O -framework AppKit -o "$APP_CONTENTS/MacOS/TokenScope" macos/launcher.swift
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $RELEASE_VERSION" "$APP_CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $RELEASE_VERSION" "$APP_CONTENTS/Info.plist"

mkdir -p release-output
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" \
  "release-output/TokenScope-$VERSION-macOS-$ARCH.zip"
