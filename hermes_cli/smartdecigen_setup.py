"""Provision the SmartDecigen layer (FORGE plugins + skin) into the active Hermes home.

Desktop users never run ``install.sh`` or ``hermes plugins enable``: the backend calls
:func:`ensure_smartdecigen_layer` on every start. The first run copies the plugins and skin,
enables the default plugin set through the plugin admission path and selects the skin. Later
runs only refresh the copied files when the shipped layer changes, so a user who disables a
plugin or picks another skin keeps that choice.

CLI users can run the same step with ``python -m hermes_cli.smartdecigen_setup``.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

LAYER_ROOT = Path(__file__).resolve().parent.parent / "smartdecigen"
DEFAULT_PLUGINS = ("forge-brain", "forge-growth", "forge-voice", "forge-exec", "forge-loop")
SKIN_NAME = "smartdecigen"
MARKER_NAME = ".smartdecigen-layer"
_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "test_*.py")


def _plugin_sources(root: Path) -> list[Path]:
    plugins = root / "plugins"
    if not plugins.is_dir():
        return []
    return sorted(p for p in plugins.iterdir() if (p / "plugin.yaml").is_file())


def layer_digest(root: Path = LAYER_ROOT) -> str:
    """Content hash of the shipped layer; a change triggers a file refresh."""
    digest = hashlib.sha256()
    files = [f for src in _plugin_sources(root) for f in sorted(src.rglob("*")) if f.is_file()]
    files.append(root / "skins" / f"{SKIN_NAME}.yaml")
    for path in files:
        if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith("test_"):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def install_layer_files(home: Path, root: Path = LAYER_ROOT) -> list[str]:
    """Copy every SmartDecigen plugin and the skin into *home*; returns the plugin names."""
    plugins_dir = home / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for src in _plugin_sources(root):
        target = plugins_dir / src.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target, ignore=_COPY_IGNORE)
        names.append(src.name)
    skin = root / "skins" / f"{SKIN_NAME}.yaml"
    if skin.is_file():
        (home / "skins").mkdir(parents=True, exist_ok=True)
        shutil.copy2(skin, home / "skins" / skin.name)
    return names


def _enable_default_plugins() -> None:
    from hermes_cli import plugins_cmd

    for name in DEFAULT_PLUGINS:
        try:
            plugins_cmd._activate_key(plugins_cmd._resolve_plugin_key(name) or name, enable=True)
        except Exception as exc:
            logger.warning("SmartDecigen: could not enable plugin %s: %s", name, exc, exc_info=True)


def _select_skin() -> None:
    from hermes_cli.config import load_config, save_config

    config = load_config()
    display = config.setdefault("display", {})
    if display.get("skin") in (None, "", "default"):
        display["skin"] = SKIN_NAME
        save_config(config)


def ensure_smartdecigen_layer(home: Path | None = None) -> bool:
    """Install/refresh the layer when needed. Returns True when anything was written.

    Never raises: a provisioning problem must not keep the backend from starting.
    """
    try:
        if not _plugin_sources(LAYER_ROOT):
            return False
        home = home or get_hermes_home()
        marker = home / MARKER_NAME
        digest = layer_digest()
        first_run = not marker.is_file()
        if not first_run and marker.read_text(encoding="utf-8-sig").strip() == digest:
            return False
        install_layer_files(home)
        if first_run:
            _enable_default_plugins()
            _select_skin()
        marker.write_text(digest, encoding="utf-8")
        return True
    except Exception as exc:
        logger.warning("SmartDecigen: layer provisioning failed: %s", exc, exc_info=True)
        return False


if __name__ == "__main__":
    changed = ensure_smartdecigen_layer()
    print("SmartDecigen layer installed." if changed else "SmartDecigen layer already up to date.")
