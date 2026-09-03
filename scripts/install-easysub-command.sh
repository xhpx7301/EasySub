#!/usr/bin/env bash
# Installs the `easysub` command while keeping the source directory configurable.

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MANAGER="$SOURCE_DIR/scripts/easysub-manager.sh"
TARGET="/usr/local/bin/easysub"

if [[ ! -f "$MANAGER" ]]; then
  printf '未找到管理脚本：%s\n' "$MANAGER" >&2
  exit 1
fi

wrapper="#!/usr/bin/env bash
exec bash \"\${EASYSUB_DIR:-$SOURCE_DIR}/scripts/easysub-manager.sh\" \"\$@\""

if [[ -w /usr/local/bin ]]; then
  printf '%s\n' "$wrapper" > "$TARGET"
  chmod 755 "$TARGET"
else
  printf '%s\n' "$wrapper" | sudo tee "$TARGET" >/dev/null
  sudo chmod 755 "$TARGET"
fi

printf '已安装命令：easysub\n'
printf '默认源码目录：%s\n' "$SOURCE_DIR"
printf '需要改用其他目录时可执行：EASYSUB_DIR=/你的目录 easysub\n'
