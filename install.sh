#!/usr/bin/env bash
#
# Link these macros into FreeCAD so a fresh install is one command away.
#
#   ./install.sh               install (safe to run again at any time)
#   ./install.sh --uninstall   remove the links this script made
#
# What it does:
#   <FreeCAD user dir>/Macro/*.FCMacro   -> symlinks to the macros in this repo
#   <FreeCAD user dir>/Mod/freecad-marcos -> symlink to this repo, so the
#                                           feature modules load as an addon
#
# The FreeCAD user dir is asked of FreeCAD itself when it can be found, so a
# new FreeCAD version folder (v1-1, v1-2, ...) is picked up automatically.
# Override it with:  FREECAD_USER_DIR=/path/to/dir ./install.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDON_NAME="freecad-marcos"
MODE="install"

case "${1:-}" in
  "" ) ;;
  --uninstall ) MODE="uninstall" ;;
  -h|--help ) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  * ) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
esac

find_freecadcmd() {
  local candidate
  for candidate in \
    "$(command -v freecadcmd 2>/dev/null || true)" \
    "$(command -v FreeCADCmd 2>/dev/null || true)" \
    "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd" \
    "$HOME/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd" \
    "/usr/bin/freecadcmd" \
    "/usr/local/bin/freecadcmd"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

find_user_dir() {
  if [ -n "${FREECAD_USER_DIR:-}" ]; then
    echo "${FREECAD_USER_DIR%/}"
    return 0
  fi

  local cmd dir
  if cmd="$(find_freecadcmd)"; then
    # Ask FreeCAD. The marker keeps the answer apart from its banner output.
    dir="$("$cmd" -c "import FreeCAD; print('USERDIR=' + FreeCAD.getUserAppDataDir())" 2>/dev/null \
           | sed -n 's/^USERDIR=//p' | tail -1)"
    if [ -n "$dir" ]; then
      echo "${dir%/}"
      return 0
    fi
  fi

  # Fallback: newest versioned folder in the usual places, else a sensible default.
  local base
  for base in "$HOME/Library/Application Support/FreeCAD" "$HOME/.local/share/FreeCAD"; do
    if [ -d "$base" ]; then
      dir="$(ls -d "$base"/v* 2>/dev/null | sort -V | tail -1 || true)"
      echo "${dir:-$base/v1-1}"
      return 0
    fi
  done
  return 1
}

if ! USER_DIR="$(find_user_dir)"; then
  echo "Could not find FreeCAD's user folder. Start FreeCAD once, or set FREECAD_USER_DIR." >&2
  exit 1
fi

MACRO_DIR="$USER_DIR/Macro"
MOD_DIR="$USER_DIR/Mod"
echo "FreeCAD user folder: $USER_DIR"

# Remove a path only if it is a symlink pointing into this repo.
remove_our_link() {
  local path="$1"
  if [ -L "$path" ]; then
    local target
    target="$(readlink "$path")"
    case "$target" in
      "$REPO"|"$REPO"/*)
        rm "$path"
        echo "  removed $path"
        ;;
    esac
  fi
}

if [ "$MODE" = "uninstall" ]; then
  for macro in "$REPO"/*.FCMacro; do
    remove_our_link "$MACRO_DIR/$(basename "$macro")"
  done
  remove_our_link "$MOD_DIR/$ADDON_NAME"
  echo "Uninstalled. Restart FreeCAD."
  exit 0
fi

mkdir -p "$MACRO_DIR" "$MOD_DIR"

echo "Macros -> $MACRO_DIR"
for macro in "$REPO"/*.FCMacro; do
  name="$(basename "$macro")"
  dest="$MACRO_DIR/$name"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    echo "  skipped $name: a real file is already there (move it away and run again)" >&2
    continue
  fi
  ln -sfn "$macro" "$dest"
  echo "  linked $name"
done

echo "Addon -> $MOD_DIR/$ADDON_NAME"
dest="$MOD_DIR/$ADDON_NAME"
if [ -e "$dest" ] && [ ! -L "$dest" ]; then
  echo "  skipped: $dest exists and is not a link (move it away and run again)" >&2
else
  ln -sfn "$REPO" "$dest"
  echo "  linked $ADDON_NAME"
fi

# Clean up layouts from earlier versions of this repo, which put the
# modules where FreeCAD refuses to reload them from.
for module in "$REPO"/*.py; do
  remove_our_link "$MACRO_DIR/$(basename "$module")"
done
if [ -d "$MOD_DIR/VoronoiCutout" ]; then
  remove_our_link "$MOD_DIR/VoronoiCutout/voronoi_cutout.py"
  rmdir "$MOD_DIR/VoronoiCutout" 2>/dev/null && echo "  removed empty $MOD_DIR/VoronoiCutout" || true
fi

echo "Done. Restart FreeCAD, then find the macros under Macro > Macros..."
