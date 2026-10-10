#!/usr/bin/env bash
# Install the SmartDecigen layer into an existing Hermes installation.
#
#   ./install.sh                 # install into $LOCALAPPDATA/hermes (default)
#   HERMES_HOME=/path/to/hermes ./install.sh
#
# Idempotent: safe to re-run. Existing files are overwritten; nothing else is touched.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$LOCALAPPDATA/hermes}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing SmartDecigen layer into: $HERMES_HOME"
echo

# --- plugins ---------------------------------------------------------------
mkdir -p "$HERMES_HOME/plugins" "$HERMES_HOME/skins"

for d in "$HERE"/smartdecigen/plugins/*/; do
  name="$(basename "$d")"
  rm -rf "$HERMES_HOME/plugins/$name"
  cp -r "$d" "$HERMES_HOME/plugins/$name"
  echo "  plugin: $name"
done

cp "$HERE/smartdecigen/plugins/README.md" "$HERMES_HOME/plugins/README.md" 2>/dev/null || true

# --- skin ------------------------------------------------------------------
cp "$HERE/smartdecigen/skins/smartdecigen.yaml" "$HERMES_HOME/skins/"
echo "  skin:   smartdecigen"

echo
echo "Installed. Next steps:"
echo
echo "  1. Enable the plugins:"
echo "       hermes plugins enable forge-brain"
echo "       hermes plugins enable forge-growth"
echo "       hermes plugins enable forge-voice"
echo "       hermes plugins enable forge-exec"
echo "       hermes plugins enable forge-loop"
echo "       # optional (both off by default):"
echo "       hermes plugins enable forge-confirm   # quality gate, costs 1 LLM call/turn"
echo "       hermes plugins enable ari-governance  # fails CLOSED, needs the ARI kernel"
echo
echo "  2. Apply the skin:"
echo "       hermes config set display.skin smartdecigen"
echo
echo "  3. Run the autonomous loop:"
echo "       hermes gateway install                                    # auto-start on login"
echo "       hermes cron create \"every 6h\" \"Run the forge business loop\" --skill forge-business-loop"
echo
echo "  4. Verify offline (no model calls):"
echo "       for p in forge-brain forge-growth forge-exec forge-loop forge-voice forge-confirm; do"
echo "         (cd \"\$HERMES_HOME/plugins/\$p\" && python -m pytest -q)"
echo "       done"
