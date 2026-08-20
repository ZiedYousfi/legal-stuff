import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import media_stack


class EnvironmentTests(unittest.TestCase):
    def test_write_and_read_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            values = {
                "MEDIA_DIR": "/media path/$disk",
                "CONFIG_DIR": "/config",
                "PUID": "1000",
                "PGID": "1000",
                "TZ": "Europe/Paris",
                "QBT_LEGAL_NOTICE": "confirm",
                "QBIT_USER": "admin",
                "QBIT_PASS": "qbit-secret",
                "SONARR_USER": "admin",
                "SONARR_PASS": "sonarr-secret",
                "SONARR_API_KEY": "0" * 32,
                "RADARR_USER": "admin",
                "RADARR_PASS": "radarr-secret",
                "RADARR_API_KEY": "1" * 32,
                "PROWLARR_USER": "admin",
                "PROWLARR_PASS": "prowlarr-secret",
            }
            media_stack.write_env(path, values)
            self.assertEqual(media_stack.read_env(path), values)

    def test_environment_write_is_private_on_unix(self):
        if media_stack.os.name == "nt":
            self.skipTest("Unix permissions are unavailable on Windows")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            media_stack.write_env(path, {"KEY": "value"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_restore_removes_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("partial", encoding="utf-8")
            media_stack.restore_file(path, None)
            self.assertFalse(path.exists())

    def test_restore_replaces_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("partial", encoding="utf-8")
            media_stack.restore_file(path, b"original")
            self.assertEqual(path.read_bytes(), b"original")

    def test_missing_required_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            media_stack.write_env(path, {"MEDIA_DIR": "/media"})
            with self.assertRaisesRegex(media_stack.StackError, "Missing required"):
                media_stack.read_env(path)


class ValidationTests(unittest.TestCase):
    def test_valid_api_key_is_normalized(self):
        key = "ABCDEF0123456789ABCDEF0123456789"
        self.assertEqual(media_stack.validate_api_key(key), key.lower())

    def test_invalid_api_key_is_rejected(self):
        with self.assertRaises(media_stack.StackError):
            media_stack.validate_api_key("not-a-key")

    def test_line_breaks_are_rejected(self):
        with self.assertRaises(media_stack.StackError):
            media_stack.dotenv_value("first\nsecond")

    @patch("builtins.input", return_value="")
    def test_qbittorrent_notice_defaults_to_yes(self, _input):
        media_stack.confirm_qbittorrent_notice()

    @patch("builtins.input", return_value="n")
    def test_qbittorrent_notice_can_be_rejected(self, _input):
        with self.assertRaisesRegex(media_stack.StackError, "not accepted"):
            media_stack.confirm_qbittorrent_notice()

    @patch("builtins.input", return_value="")
    def test_username_defaults_to_admin(self, _input):
        self.assertEqual(media_stack.prompt_username("Sonarr"), "admin")

    @patch("media_stack.getpass.getpass", side_effect=("secret", "secret"))
    def test_password_requires_confirmation(self, _getpass):
        self.assertEqual(media_stack.prompt_password("Sonarr"), "secret")

    def test_temporary_qbittorrent_password_is_extracted(self):
        logs = (
            "The WebUI administrator password was not set. "
            "A temporary password is provided for this session: AbC123xy"
        )
        self.assertEqual(
            media_stack.temporary_qbittorrent_password(logs), "AbC123xy"
        )

    def test_missing_temporary_qbittorrent_password_is_rejected(self):
        with self.assertRaisesRegex(media_stack.StackError, "did not publish"):
            media_stack.temporary_qbittorrent_password("qBittorrent started")


class SetupGuideTests(unittest.TestCase):
    def guide_output(self, printer, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            printer(*arguments)
        return output.getvalue()

    def test_qbittorrent_guide_contains_login_and_ui_path(self):
        output = self.guide_output(
            media_stack.print_qbittorrent_guide, "Temporary123"
        )
        self.assertIn("http://localhost:8080", output)
        self.assertIn("Temporary password: Temporary123", output)
        self.assertIn("Tools > Options > Web UI", output)
        self.assertIn("/media/Downloads", output)

    def test_service_guides_contain_urls_and_media_paths(self):
        guides = (
            (media_stack.print_sonarr_guide, "http://localhost:8989", "/media/Series"),
            (media_stack.print_radarr_guide, "http://localhost:7878", "/media/Movies"),
            (media_stack.print_prowlarr_guide, "http://localhost:9696", "http://sonarr:8989"),
            (media_stack.print_jellyfin_guide, "http://localhost:8096", "/media/Movies"),
        )
        for printer, url, path in guides:
            with self.subTest(url=url):
                output = self.guide_output(printer)
                self.assertIn(url, output)
                self.assertIn(path, output)


class StartupTests(unittest.TestCase):
    def test_user_systemd_unit_has_no_root_user(self):
        unit = media_stack.systemd_unit(
            Path("/repo/media_stack.py"), Path("/usr/bin/python")
        )
        self.assertIn("WantedBy=default.target", unit)
        self.assertNotIn("User=", unit)

    def test_system_systemd_unit_uses_selected_user(self):
        unit = media_stack.systemd_unit(
            Path("/repo/media_stack.py"), Path("/usr/bin/python"), "alice"
        )
        self.assertIn("User=alice", unit)
        self.assertIn("Requires=docker.service", unit)
        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertIn("TimeoutStartSec=infinity", unit)

    def test_systemd_unit_quotes_paths(self):
        unit = media_stack.systemd_unit(
            Path("/repo with spaces/media_stack.py"), Path("/usr/bin/python")
        )
        self.assertIn("'/repo with spaces/media_stack.py'", unit)

    def test_windows_launcher_is_hidden(self):
        launcher = media_stack.windows_launcher(
            Path("C:/stack/media_stack.py"),
            Path("C:/Python/pythonw.exe"),
            Path("C:/stack/config/startup.log"),
        )
        self.assertIn(", 0, False", launcher)
        self.assertIn("media_stack.py", launcher)


class DockerTests(unittest.TestCase):
    @patch("media_stack.shutil.which", return_value=None)
    def test_missing_docker_is_reported(self, _which):
        with self.assertRaisesRegex(media_stack.StackError, "not installed"):
            media_stack.wait_for_docker(timeout=0)

    @patch("media_stack.restore_file")
    @patch("media_stack.compose", side_effect=OSError("docker disappeared"))
    def test_rollback_restores_environment_when_docker_cleanup_fails(
        self, _compose, restore_file
    ):
        with contextlib.redirect_stderr(io.StringIO()):
            media_stack.rollback_setup(b"old environment", stop_stack=True)
        restore_file.assert_called_once_with(
            media_stack.ENV_FILE, b"old environment"
        )

    @patch("media_stack.restore_file")
    @patch("media_stack.compose")
    def test_rollback_preserves_preexisting_stack(self, compose, restore_file):
        media_stack.rollback_setup(b"old environment", stop_stack=False)
        compose.assert_not_called()
        restore_file.assert_called_once_with(
            media_stack.ENV_FILE, b"old environment"
        )


class CommandHelpTests(unittest.TestCase):
    def help_output(self, arguments):
        output = io.StringIO()
        with self.assertRaises(SystemExit) as exit_context:
            with contextlib.redirect_stdout(output):
                media_stack.parse_arguments(arguments)
        self.assertEqual(exit_context.exception.code, 0)
        return output.getvalue()

    def test_help_argument_matches_help_flag(self):
        self.assertEqual(self.help_output(["help"]), self.help_output(["-h"]))

    def test_general_help_describes_every_command(self):
        output = " ".join(self.help_output(["help"]).split())
        for description in (
            "Configure credentials, services, Recyclarr, and automatic startup.",
            "Start the services and synchronize Recyclarr.",
            "Stop and remove the stack containers.",
            "Show the current service status.",
        ):
            self.assertIn(description, output)

    def test_empty_arguments_show_general_help(self):
        self.assertEqual(self.help_output([]), self.help_output(["help"]))

    def test_each_command_has_detailed_help(self):
        expected = {
            "setup": "Configure credentials, start the services",
            "start": "Start the media services",
            "stop": "Stop and remove the media stack containers",
            "status": "Show the current Docker Compose status",
        }
        for command, description in expected.items():
            with self.subTest(command=command):
                self.assertIn(description, self.help_output([command, "-h"]))


if __name__ == "__main__":
    unittest.main()
