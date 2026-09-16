#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
variant="$1"
case "$variant" in Intel|Apple-Silicon) ;; *) exit 2 ;; esac
stage=$(mktemp -d)
mount_dir=$(mktemp -d)
image_path="$(pwd)/dist/ImageDesk-2.0-macOS-${variant}.dmg"
ditto dist/ImageDesk.app "$stage/ImageDesk.app"
ln -s /Applications "$stage/Applications"
hdiutil create -volname 'Image Desk' -srcfolder "$stage" -ov -format UDZO "$image_path"
hdiutil verify "$image_path"
hdiutil attach -readonly -nobrowse -mountpoint "$mount_dir" "$image_path"
test -x "$mount_dir/ImageDesk.app/Contents/MacOS/ImageDesk"
hdiutil detach "$mount_dir"
rm -rf "$stage"
rmdir "$mount_dir"
