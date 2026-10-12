"""SmartDecigen first-run provisioning: files, default plugin set, skin, idempotence."""
from unittest import mock

from hermes_cli import smartdecigen_setup as setup
from hermes_cli.config import load_config
from hermes_constants import get_hermes_home


def test_first_run_installs_layer_enables_defaults_and_selects_skin():
    home = get_hermes_home()
    activated = []
    with mock.patch("hermes_cli.plugins_cmd._activate_key",
                    side_effect=lambda key, enable: activated.append((key, enable))):
        assert setup.ensure_smartdecigen_layer() is True

    for name in ("forge-brain", "forge-confirm", "ari-governance"):
        assert (home / "plugins" / name / "plugin.yaml").is_file()
    assert not list((home / "plugins").rglob("test_*.py"))
    assert (home / "skins" / "smartdecigen.yaml").is_file()
    assert [enable for _, enable in activated] == [True] * len(setup.DEFAULT_PLUGINS)
    assert {key.rsplit("/", 1)[-1] for key, _ in activated} == set(setup.DEFAULT_PLUGINS)
    assert load_config()["display"]["skin"] == "smartdecigen"


def test_later_runs_keep_user_choices_and_only_refresh_changed_files():
    home = get_hermes_home()
    with mock.patch("hermes_cli.plugins_cmd._activate_key"):
        setup.ensure_smartdecigen_layer()
    with mock.patch("hermes_cli.plugins_cmd._activate_key") as activate:
        assert setup.ensure_smartdecigen_layer() is False
        (home / setup.MARKER_NAME).write_text("older-layer", encoding="utf-8")
        (home / "plugins" / "forge-brain" / "plugin.yaml").unlink()
        assert setup.ensure_smartdecigen_layer() is True
    activate.assert_not_called()
    assert (home / "plugins" / "forge-brain" / "plugin.yaml").is_file()


def test_failures_never_escape():
    with mock.patch.object(setup, "install_layer_files", side_effect=OSError("read-only")):
        assert setup.ensure_smartdecigen_layer() is False
