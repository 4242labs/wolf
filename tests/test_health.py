from unittest.mock import patch

from wolf.health import check_command, check_service


def test_check_service_uses_systemd_when_available():
    with (
        patch("wolf.health.shutil.which", return_value="/usr/bin/systemctl"),
        patch("wolf.health._systemd_service_active", return_value=True) as mocked,
    ):
        result = check_service("Docker", "docker")
    mocked.assert_called_once_with("docker", False)
    assert result.ok is True
    assert result.detail == "active"


def test_check_service_falls_back_on_non_systemd_host():
    with (
        patch("wolf.health.shutil.which", return_value=None),
        patch("wolf.health._command_exits_zero", return_value=True) as mocked,
    ):
        result = check_service("Docker", "docker")
    mocked.assert_called_once_with(["docker", "info"])
    assert result.ok is True


def test_check_service_fallback_ssh_uses_tcp_port():
    with (
        patch("wolf.health.shutil.which", return_value=None),
        patch("wolf.health._tcp_port_open", return_value=False) as mocked,
    ):
        result = check_service("SSH", "ssh")
    mocked.assert_called_once_with("127.0.0.1", 22)
    assert result.ok is False


def test_check_service_fallback_tailscale_uses_interface_check():
    with (
        patch("wolf.health.shutil.which", return_value=None),
        patch("wolf.health._tailscale_interface_up", return_value=True) as mocked,
    ):
        result = check_service("Tailscale", "tailscaled")
    mocked.assert_called_once_with()
    assert result.ok is True


def test_check_service_unknown_label_has_no_fallback():
    with patch("wolf.health.shutil.which", return_value=None):
        result = check_service("Something Else", "something")
    assert result.ok is False
    assert "no non-systemd fallback" in result.detail


def test_check_command_reports_path_when_present():
    with patch("wolf.health.shutil.which", return_value="/usr/bin/gh"):
        result = check_command("GitHub CLI", "gh")
    assert result.ok is True
    assert result.detail == "/usr/bin/gh"


def test_check_command_reports_missing():
    with patch("wolf.health.shutil.which", return_value=None):
        result = check_command("GitHub CLI", "gh")
    assert result.ok is False
    assert result.detail == "missing"
