"""Real end-to-end tests: install the package and drive the installed console script.

They run the real lvext executable as a subprocess and assert its actual output and
exit status: the console script of the installed wheel when the suite runs against
one, otherwise a throwaway venv with this checkout installed (editable). Nothing is
mocked.
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
    """Return the console script under test.

    When lvext is imported from an installed wheel (the suite run from the sdist with
    ``src`` removed), that is the script installed next to this interpreter. Otherwise a
    throwaway venv gets an editable install of this checkout.
    """
    scripts_name = "Scripts" if sys.platform == "win32" else "bin"
    exe_name = "lvext.exe" if sys.platform == "win32" else "lvext"
    if _PROJECT_ROOT / "src" not in Path(lvext.__file__).resolve().parents:
        installed = Path(sys.executable).parent / exe_name
        if not installed.is_file():
            installed = Path(sys.prefix) / scripts_name / exe_name
        assert installed.is_file(), f"installed console script missing at {installed}"
        return installed
    env_dir = tmp_path_factory.mktemp("lvext_e2e_env")
    venv.create(env_dir, with_pip=True)
    scripts = env_dir / scripts_name
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "-e", str(_PROJECT_ROOT)],
        check=True,
        capture_output=True,
    )
    executable = scripts / exe_name
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


def test_flattened_round_trip_through_the_cli(cli: Path) -> None:
    flat = _run(cli, "encode", "1/3", "--flattened").stdout.strip()
    assert flat == "3ffd5555555555555556" + "0" * 12
    report = json.loads(_run(cli, "decode", flat, "--flattened", "--json").stdout)
    assert report["mantissa"] == "0xaaaaaaaaaaaaaaab"
    assert report["flattened"] == flat


def test_the_script_is_the_version_under_test(cli: Path) -> None:
    result = _run(cli, "decode", "3fff8000000000000000", "--json")
    assert json.loads(result.stdout)["flattened"] == "3fff" + "0" * 28
