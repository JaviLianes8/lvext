"""Real end-to-end tests: install the package and drive the installed console script.

These build a throwaway virtual environment, pip-install lvext into it (editable),
and run the real lvext executable as a subprocess, asserting its actual output and
exit status. Nothing is mocked.
"""

import json
import subprocess
import sys
import venv
from pathlib import Path

import pytest

import lvext

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a venv, install lvext editable, return the console script path."""
    env_dir = tmp_path_factory.mktemp("lvext_e2e_env")
    venv.create(env_dir, with_pip=True)
    scripts = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "-e", str(_PROJECT_ROOT)],
        check=True,
        capture_output=True,
    )
    executable = scripts / ("lvext.exe" if sys.platform == "win32" else "lvext")
    assert executable.is_file(), f"console script not installed at {executable}"
    return executable


def _run(cli: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(cli), *args], capture_output=True, text=True, timeout=60)


def test_version_reports_the_package_version(cli: Path) -> None:
    result = _run(cli, "--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"lvext {lvext.__version__}"


def test_help_shows_runnable_examples(cli: Path) -> None:
    result = _run(cli, "--help")
    assert result.returncode == 0
    assert "lvext encode 1" in result.stdout
    assert "lvext decode 3ffd8000000000000000" in result.stdout


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", "3fff8000000000000000"),
        ("0.25", "3ffd8000000000000000"),
        ("-2.5", "c000a000000000000000"),
        ("1/3", "3ffdaaaaaaaaaaaaaaab"),
    ],
)
def test_encode_golden_vectors(cli: Path, value: str, expected: str) -> None:
    result = _run(cli, "encode", value)
    assert (result.returncode, result.stdout.strip(), result.stderr) == (0, expected, "")


def test_encode_then_decode_round_trips_through_the_cli(cli: Path) -> None:
    encoded = _run(cli, "encode", "0.1").stdout.strip()
    assert encoded == "3ffbcccccccccccccccd"
    report = json.loads(_run(cli, "decode", encoded, "--json").stdout)
    assert report["kind"] == "normal"
    assert report["exact"].startswith("0.1000000000000000000013552527156068805425")
    assert report["float"] == "0.1"
    assert report["float_exact"] is False


def test_decode_smallest_subnormal(cli: Path) -> None:
    result = _run(cli, "decode", "00000000000000000001")
    assert result.returncode == 0
    assert "kind: subnormal" in result.stdout
    assert "exact: 3.6451995318824746025" in result.stdout
    assert "float: 0.0" in result.stdout


def test_bad_hex_errors_to_stderr_with_exit_1(cli: Path) -> None:
    result = _run(cli, "decode", "xyz")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "hex digits" in result.stderr


def test_missing_command_exits_1(cli: Path) -> None:
    result = _run(cli)
    assert result.returncode == 1
    assert "usage" in result.stderr
