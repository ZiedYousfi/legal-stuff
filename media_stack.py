#!/usr/bin/env python3
"""Set up and operate the local media stack without external dependencies."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
CONFIG_TEMPLATE = ROOT / "recyclarr" / "recyclarr.yml"
CORE_SERVICES = ("jellyfin", "qbittorrent", "prowlarr", "sonarr", "radarr")
API_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
QBIT_TEMP_PASSWORD_PATTERN = re.compile(
    r"temporary password is provided for this session:\s*(\S+)", re.IGNORECASE
)
DOCKER_WAIT_SECONDS = 300


class StackError(RuntimeError):
    pass


def run(
    command: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        capture_output=capture_output,
        input=input_text,
        text=True,
    )


def compose(*arguments: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return run(("docker", "compose", *arguments), **kwargs)


def wait_for_docker(
    timeout: int = DOCKER_WAIT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run,
) -> None:
    if shutil.which("docker") is None:
        raise StackError(
            "Docker is not installed. Follow https://docs.docker.com/get-docker/."
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = runner(
            ("docker", "info"), check=False, capture_output=True
        )
        if result.returncode == 0:
            compose_result = runner(
                ("docker", "compose", "version"),
                check=False,
                capture_output=True,
            )
            if compose_result.returncode == 0:
                return
            raise StackError(
                "Docker Compose is unavailable. Follow "
                "https://docs.docker.com/compose/install/."
            )
        time.sleep(2)

    raise StackError("Docker did not become ready within five minutes.")


def dotenv_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise StackError("Environment values cannot contain line breaks.")
    return json.dumps(value.replace("$", "$$"), ensure_ascii=True)


def write_env(path: Path, values: Mapping[str, str]) -> None:
    content = "".join(f"{key}={dotenv_value(value)}\n" for key, value in values.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
        if os.name != "nt":
            path.chmod(0o600)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def restore_file(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def read_env(path: Path = ENV_FILE) -> dict[str, str]:
    if not path.exists():
        raise StackError("Run 'python media_stack.py setup' first.")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        try:
            values[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            values[key] = raw_value
        values[key] = str(values[key]).replace("$$", "$")

    required = {
        "MEDIA_DIR",
        "CONFIG_DIR",
        "PUID",
        "PGID",
        "TZ",
        "QBT_LEGAL_NOTICE",
        "QBIT_USER",
        "QBIT_PASS",
        "SONARR_USER",
        "SONARR_PASS",
        "SONARR_API_KEY",
        "RADARR_USER",
        "RADARR_PASS",
        "RADARR_API_KEY",
        "PROWLARR_USER",
        "PROWLARR_PASS",
    }
    missing = sorted(key for key in required if not values.get(key))
    if missing:
        raise StackError(f"Missing required .env values: {', '.join(missing)}")
    for key in ("MEDIA_DIR", "CONFIG_DIR"):
        if not Path(values[key]).is_absolute():
            raise StackError(f"{key} must be an absolute path.")
    validate_api_key(values["SONARR_API_KEY"])
    validate_api_key(values["RADARR_API_KEY"])
    if values["QBT_LEGAL_NOTICE"] != "confirm":
        raise StackError("qBittorrent's legal notice is not confirmed in .env.")
    return values


def normalized_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    try:
        return path.resolve()
    except OSError as error:
        raise StackError(f"Cannot resolve path: {raw_path}") from error


def compose_path(path: Path) -> str:
    return path.as_posix()


def user_ids() -> tuple[str, str]:
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        return str(os.getuid()), str(os.getgid())
    return "1000", "1000"


def validate_api_key(value: str) -> str:
    value = value.strip()
    if not API_KEY_PATTERN.fullmatch(value):
        raise StackError("API keys must contain exactly 32 hexadecimal characters.")
    return value.lower()


def prompt_api_key(service: str) -> str:
    while True:
        try:
            return validate_api_key(input(f"Paste the {service} API key: "))
        except StackError as error:
            print(f"Error: {error}")


def confirm_qbittorrent_notice() -> None:
    while True:
        answer = input("Accept qBittorrent's legal notice? [Y/n]: ").strip().lower()
        if answer in {"", "y", "yes"}:
            return
        if answer in {"n", "no"}:
            raise StackError("qBittorrent's legal notice was not accepted.")
        print("Enter Y or N.")


def prompt_username(service: str, default: str = "admin") -> str:
    value = input(f"{service} username [{default}]: ").strip()
    return value or default


def prompt_password(service: str) -> str:
    while True:
        password = getpass.getpass(f"{service} password: ")
        if not password:
            print("Password cannot be empty.")
            continue
        confirmation = getpass.getpass(f"Repeat {service} password: ")
        if password == confirmation:
            return password
        print("Passwords do not match.")


def prompt_credentials() -> dict[str, str]:
    credentials: dict[str, str] = {}
    for key, service in (
        ("QBIT", "qBittorrent"),
        ("SONARR", "Sonarr"),
        ("RADARR", "Radarr"),
        ("PROWLARR", "Prowlarr"),
    ):
        credentials[f"{key}_USER"] = prompt_username(service)
        credentials[f"{key}_PASS"] = prompt_password(service)
    return credentials


def create_directories(media_dir: Path, config_dir: Path) -> None:
    for directory in ("Movies", "Series", "Downloads"):
        (media_dir / directory).mkdir(parents=True, exist_ok=True)
    for directory in (
        "jellyfin",
        "jellyfin-cache",
        "qbittorrent",
        "prowlarr",
        "sonarr",
        "radarr",
        "recyclarr",
        "recyclarr-data",
    ):
        (config_dir / directory).mkdir(parents=True, exist_ok=True)


def copy_recyclarr_config(config_dir: Path) -> None:
    destination = config_dir / "recyclarr" / "recyclarr.yml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONFIG_TEMPLATE, destination)


def temporary_qbittorrent_password(logs: str) -> str:
    match = QBIT_TEMP_PASSWORD_PATTERN.search(logs)
    if not match:
        raise StackError("qBittorrent did not publish a temporary Web UI password.")
    return match.group(1)


def wait_for_qbittorrent_password(timeout: int = 60) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = compose("logs", "--no-color", "qbittorrent", capture_output=True)
        try:
            return temporary_qbittorrent_password(result.stdout + result.stderr)
        except StackError:
            time.sleep(2)
    raise StackError(
        "qBittorrent did not publish a temporary Web UI password within one minute."
    )


def print_qbittorrent_guide(password: str | None) -> None:
    temporary_login = (
        f"Temporary username: admin\nTemporary password: {password}"
        if password
        else "Use the existing permanent credentials stored in .env."
    )
    print(
        f"""
qBittorrent setup

Open this link:
http://localhost:8080

{temporary_login}

1. Sign in to the Web UI.
2. Open Tools > Options > Web UI.
3. Find the Authentication section.
4. Set Username to the QBIT_USER value stored in .env.
5. Set Password to the QBIT_PASS value stored in .env.
6. Open the Downloads section.
7. Find Saving Management > Default Save Path.
8. Set it to /media/Downloads.
9. Click Apply, then OK.
""".strip()
    )


def print_sonarr_guide() -> None:
    print(
        """
Sonarr setup

Open this link:
http://localhost:8989

1. Complete first-run authentication with SONARR_USER and SONARR_PASS from .env.
2. Open Settings > Media Management.
3. Under Root Folders, click Add Root Folder.
4. Select /media/Series and save it.
5. Open Settings > Download Clients.
6. Click Add, then select qBittorrent.
7. Set Host to qbittorrent and Port to 8080.
8. Use QBIT_USER and QBIT_PASS from .env.
9. Set Category to sonarr.
10. Click Test, then Save.
11. Open Settings > General > Security.
12. Copy the API Key for the next terminal prompt.
""".strip()
    )


def print_radarr_guide() -> None:
    print(
        """
Radarr setup

Open this link:
http://localhost:7878

1. Complete first-run authentication with RADARR_USER and RADARR_PASS from .env.
2. Open Settings > Media Management.
3. Under Root Folders, click Add Root Folder.
4. Select /media/Movies and save it.
5. Open Settings > Download Clients.
6. Click Add, then select qBittorrent.
7. Set Host to qbittorrent and Port to 8080.
8. Use QBIT_USER and QBIT_PASS from .env.
9. Set Category to radarr.
10. Click Test, then Save.
11. Open Settings > General > Security.
12. Copy the API Key for the next terminal prompt.
""".strip()
    )


def print_prowlarr_guide() -> None:
    print(
        """
Prowlarr setup

Open this link:
http://localhost:9696

1. Complete first-run authentication with PROWLARR_USER and PROWLARR_PASS from .env.
2. Open Settings > Apps.
3. Click Add, then select Sonarr.
4. Set Sync Level to Full Sync.
5. Set Prowlarr Server to http://prowlarr:9696.
6. Set Sonarr Server to http://sonarr:8989.
7. Use the SONARR_API_KEY value now stored in .env.
8. Click Test, then Save.
9. Click Add, then select Radarr.
10. Set Sync Level to Full Sync.
11. Set Prowlarr Server to http://prowlarr:9696.
12. Set Radarr Server to http://radarr:7878.
13. Use the RADARR_API_KEY value now stored in .env.
14. Click Test, then Save.
15. Open Indexers, add your indexers, then test each one.
""".strip()
    )


def print_jellyfin_guide() -> None:
    print(
        """
Jellyfin setup

Open this link:
http://localhost:8096

1. Select the display language.
2. Create the Jellyfin administrator account.
3. Do not reuse credentials from .env for Jellyfin.
4. Add a Movies library using /media/Movies.
5. Add a Shows library using /media/Series.
6. Complete the remaining setup wizard pages.
""".strip()
    )


def wait_for_step(service: str) -> None:
    input(f"\nPress Enter when {service} is configured.")


def media_stack_is_running() -> bool:
    result = run(
        (
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=media-stack",
            "--quiet",
        ),
        capture_output=True,
    )
    return bool(result.stdout.strip())


def rollback_setup(previous_env: bytes | None, stop_stack: bool) -> None:
    try:
        if stop_stack:
            compose("down", check=False)
    except OSError as error:
        print(f"Warning: could not stop the partial stack: {error}", file=sys.stderr)
    finally:
        restore_file(ENV_FILE, previous_env)


def wait_for_api(name: str, url: str, api_key: str, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    request = urllib.request.Request(url, headers={"X-Api-Key": api_key})
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2)
    raise StackError(f"{name} did not become ready within three minutes.")


def wait_for_apps(values: Mapping[str, str]) -> None:
    wait_for_api(
        "Sonarr",
        "http://127.0.0.1:8989/api/v3/system/status",
        values["SONARR_API_KEY"],
    )
    wait_for_api(
        "Radarr",
        "http://127.0.0.1:7878/api/v3/system/status",
        values["RADARR_API_KEY"],
    )


def sync_recyclarr(values: Mapping[str, str]) -> None:
    config_dir = Path(values["CONFIG_DIR"])
    copy_recyclarr_config(config_dir)
    wait_for_apps(values)
    compose("run", "--rm", "recyclarr", "sync")


def systemd_unit(script: Path, python: Path, user: str | None = None) -> str:
    user_line = f"User={user}\n" if user else ""
    docker_dependency = (
        "Requires=docker.service\nAfter=docker.service network-online.target\n"
        if user
        else ""
    )
    target = "multi-user.target" if user else "default.target"
    script_arg = shlex.quote(str(script))
    python_arg = shlex.quote(str(python))
    root_arg = shlex.quote(str(ROOT))
    log_arg = shlex.quote(str(ROOT / "config" / "startup.log"))
    return (
        "[Unit]\n"
        "Description=Media stack\n"
        f"{docker_dependency}"
        "\n[Service]\n"
        "Type=oneshot\n"
        "RemainAfterExit=yes\n"
        f"{user_line}"
        f"WorkingDirectory={root_arg}\n"
        f"ExecStart={python_arg} {script_arg} start --log-file {log_arg}\n"
        f"ExecStop={python_arg} {script_arg} stop\n"
        "TimeoutStartSec=infinity\n"
        "\n[Install]\n"
        f"WantedBy={target}\n"
    )


def install_linux_autostart() -> None:
    print("\nLinux automatic start:")
    print("1. User service (starts with this user's systemd session)")
    print("2. System service (starts at boot and requires sudo)")
    choice = input("Choose 1 or 2: ").strip()
    if choice not in {"1", "2"}:
        raise StackError("Automatic start choice must be 1 or 2.")

    script = Path(__file__).resolve()
    python = Path(sys.executable).resolve()
    if choice == "1":
        unit_path = Path.home() / ".config/systemd/user/media-stack.service"
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(systemd_unit(script, python), encoding="utf-8")
        run(("systemctl", "--user", "daemon-reload"))
        run(("systemctl", "--user", "enable", "media-stack.service"))
        print(f"Installed {unit_path}")
        return

    user = os.environ.get("USER")
    if not user:
        raise StackError("Cannot determine the current Linux user.")
    unit = systemd_unit(script, python, user)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(unit)
        temporary_unit = Path(handle.name)
    try:
        run(("sudo", "install", "-m", "644", str(temporary_unit), "/etc/systemd/system/media-stack.service"))
        run(("sudo", "systemctl", "daemon-reload"))
        run(("sudo", "systemctl", "enable", "media-stack.service"))
    finally:
        temporary_unit.unlink(missing_ok=True)
    print("Installed /etc/systemd/system/media-stack.service")


def windows_launcher(script: Path, pythonw: Path, log_file: Path) -> str:
    command = f'"{pythonw}" "{script}" start --log-file "{log_file}"'
    escaped = command.replace('"', '""')
    return (
        'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.Run "{escaped}", 0, False\n'
    )


def install_windows_autostart() -> None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise StackError("APPDATA is unavailable; cannot find the Startup folder.")
    startup = Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    if not pythonw.exists():
        raise StackError("pythonw.exe is required for hidden Windows startup.")
    launcher = startup / "media-stack.vbs"
    launcher.write_text(
        windows_launcher(
            Path(__file__).resolve(), pythonw, ROOT / "config" / "startup.log"
        ),
        encoding="utf-8",
    )
    print(f"Installed {launcher}")


def install_autostart() -> None:
    if os.name == "nt":
        install_windows_autostart()
    elif sys.platform.startswith("linux"):
        install_linux_autostart()
    else:
        raise StackError("Automatic start is supported only on Windows and Linux.")


def setup() -> None:
    wait_for_docker()
    print("This setup overwrites .env on every completed run.")
    print("It does not migrate named volumes created by the previous stack.")
    print("Existing named volumes are left untouched for manual recovery.")
    media_dir = normalized_path(input("Media directory: ").strip())
    confirm_qbittorrent_notice()

    config_dir = (ROOT / "config").resolve()
    puid, pgid = user_ids()
    values = {
        "MEDIA_DIR": compose_path(media_dir),
        "CONFIG_DIR": compose_path(config_dir),
        "PUID": puid,
        "PGID": pgid,
        "TZ": "Europe/Paris",
        "QBT_LEGAL_NOTICE": "confirm",
        "SONARR_API_KEY": "",
        "RADARR_API_KEY": "",
    }
    values.update(prompt_credentials())
    create_directories(media_dir, config_dir)
    qbittorrent_was_configured = any(
        (config_dir / "qbittorrent").rglob("qBittorrent.conf")
    )
    stack_was_running = media_stack_is_running()
    previous_env = ENV_FILE.read_bytes() if ENV_FILE.exists() else None
    setup_complete = False
    stack_mutation_started = False
    write_env(ENV_FILE, values)
    try:
        compose("config", "--quiet")
        stack_mutation_started = True
        compose("up", "-d", *CORE_SERVICES)

        temporary_password = (
            None if qbittorrent_was_configured else wait_for_qbittorrent_password()
        )
        print_qbittorrent_guide(temporary_password)
        wait_for_step("qBittorrent")

        print_sonarr_guide()
        wait_for_step("Sonarr")
        values["SONARR_API_KEY"] = prompt_api_key("Sonarr")

        print_radarr_guide()
        wait_for_step("Radarr")
        values["RADARR_API_KEY"] = prompt_api_key("Radarr")
        write_env(ENV_FILE, values)

        print_prowlarr_guide()
        wait_for_step("Prowlarr")

        print_jellyfin_guide()
        wait_for_step("Jellyfin")

        sync_recyclarr(values)
        install_autostart()
        setup_complete = True
    finally:
        if not setup_complete:
            rollback_setup(
                previous_env,
                stop_stack=stack_mutation_started and not stack_was_running,
            )
    print("\nSetup complete. Use 'python media_stack.py status' to inspect it.")


def start() -> None:
    values = read_env()
    wait_for_docker()
    compose("up", "-d", *CORE_SERVICES)
    sync_recyclarr(values)


def stop() -> None:
    wait_for_docker()
    compose("down")


def status() -> None:
    wait_for_docker()
    compose("ps")


def configure_logging(log_file: str | None) -> None:
    if not log_file:
        return
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = handle
    sys.stderr = handle
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] media-stack start")


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(arguments) if arguments is not None else sys.argv[1:]
    if not arguments or arguments == ["help"]:
        arguments = ["-h"]

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", metavar="command", required=True)

    setup_parser = commands.add_parser(
        "setup",
        help="Configure credentials, services, Recyclarr, and automatic startup.",
        description="Configure credentials, start the services, apply Recyclarr profiles, and install automatic startup.",
    )
    setup_parser.set_defaults(handler=setup)

    start_parser = commands.add_parser(
        "start",
        help="Start the services and synchronize Recyclarr.",
        description="Start the media services, wait for Sonarr and Radarr, then synchronize Recyclarr.",
    )
    start_parser.add_argument("--log-file", help=argparse.SUPPRESS)
    start_parser.set_defaults(handler=start)

    stop_parser = commands.add_parser(
        "stop",
        help="Stop and remove the stack containers.",
        description="Stop and remove the media stack containers and network while preserving configuration and media files.",
    )
    stop_parser.set_defaults(handler=stop)

    status_parser = commands.add_parser(
        "status",
        help="Show the current service status.",
        description="Show the current Docker Compose status for every media stack service.",
    )
    status_parser.set_defaults(handler=status)

    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    configure_logging(getattr(options, "log_file", None))
    try:
        options.handler()
    except KeyboardInterrupt:
        print("\nCommand cancelled.", file=sys.stderr)
        return 130
    except (StackError, subprocess.CalledProcessError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
