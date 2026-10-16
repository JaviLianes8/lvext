import json

import pytest

from lvext import __version__
from lvext._cli import main

Capture = pytest.CaptureFixture[str]


def _run(capsys: Capture, *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_encode_prints_big_endian_hex(capsys: Capture) -> None:
    assert _run(capsys, "encode", "-2.5") == (0, "c000a000000000000000\n", "")


def test_encode_options(capsys: Capture) -> None:
    assert _run(capsys, "encode", "1", "--byteorder", "little")[1] == "0000000000000080ff3f\n"
    assert _run(capsys, "encode", "1", "--width", "16")[1] == "0000000000003fff8000000000000000\n"
    third = _run(capsys, "encode", "1/3", "--rounding", "toward-zero")
    assert third[1] == "3ffdaaaaaaaaaaaaaaaa\n"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("inf", "7fff8000000000000000"),
        ("-inf", "ffff8000000000000000"),
        ("nan", "7fffc000000000000000"),
        ("snan", "7fff8000000000000001"),
        ("-0", "80000000000000000000"),
        ("1e-5000", "00000000000000000000"),
    ],
)
def test_encode_special_values(capsys: Capture, value: str, expected: str) -> None:
    assert _run(capsys, "encode", "--", value)[1] == expected + "\n"


def test_decode_text_report(capsys: Capture) -> None:
    code, out, _ = _run(capsys, "decode", "3ffd 8000 0000 0000 0000")
    assert code == 0
    assert "kind: normal\n" in out
    assert "exact: 0.25\n" in out
    assert "float: 0.25\n" in out
    assert "float_exact: yes\n" in out


def test_decode_json_report(capsys: Capture) -> None:
    code, out, _ = _run(capsys, "decode", "4000c90fdaa22168c235", "--json")
    report = json.loads(out)
    assert code == 0
    assert report["exact"] == "3.14159265358979323851280895940618620443274267017841339111328125"
    assert report["float"] == "3.141592653589793"
    assert report["float_hex"] == "400921fb54442d18"
    assert report["float_exact"] is False


def test_decode_rejected_encoding(capsys: Capture) -> None:
    report = json.loads(_run(capsys, "decode", "7fff0000000000000000", "--json")[1])
    assert report["kind"] == "pseudo-infinity"
    assert report["exact"] is None
    assert report["float_hex"] == "fff8000000000000"
    text = _run(capsys, "decode", "7fff0000000000000000")[1]
    assert "exact: none (rejected by the 80387 and later)" in text


def test_decode_padded_and_little_endian(capsys: Capture) -> None:
    padded = _run(capsys, "decode", "ffffffffffff3fff8000000000000000", "--json")[1]
    assert json.loads(padded)["exact"] == "1"
    little = _run(capsys, "decode", "0000000000000080ff3f", "--byteorder", "little", "--json")
    assert json.loads(little[1])["exact"] == "1"


def test_decode_rounding_option(capsys: Capture) -> None:
    out = _run(capsys, "decode", "7ffeffffffffffffffff", "--rounding", "toward-zero", "--json")
    assert json.loads(out[1])["float"] == "1.7976931348623157e+308"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("encode", "abc"), "not a number"),
        (("encode", "1/0"), "not a number"),
        (("decode", "zz"), "20 or 32 hex digits"),
        (("decode", "z" * 20), "not a hex string"),
        (("decode", "z" * 32), "not a hex string"),
    ],
)
def test_bad_input_errors_to_stderr_with_exit_1(
    capsys: Capture, args: tuple[str, ...], message: str
) -> None:
    code, out, err = _run(capsys, *args)
    assert (code, out) == (1, "")
    assert message in err


def test_usage_errors_exit_1(capsys: Capture) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["encode", "1", "--rounding", "up"])
    assert exc.value.code == 1
    assert "invalid choice" in capsys.readouterr().err


def test_version(capsys: Capture) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out == f"lvext {__version__}\n"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("encode", "-1e-4000"), "8c179c3d73864f3805c0"),
        (("encode", "-1/3"), "bffdaaaaaaaaaaaaaaab"),
        (("encode", "-inf"), "ffff8000000000000000"),
        (("encode", "-nan"), "ffffc000000000000000"),
        (("encode", "--rounding", "floor", "-1/3"), "bffdaaaaaaaaaaaaaaab"),
        (("encode", "-1/3", "--rounding", "ceiling"), "bffdaaaaaaaaaaaaaaaa"),
        (("encode", "--", "-1/3"), "bffdaaaaaaaaaaaaaaab"),
    ],
)
def test_negative_values_need_no_separator(
    capsys: Capture, args: tuple[str, ...], expected: str
) -> None:
    assert _run(capsys, *args) == (0, expected + "\n", "")


def test_decode_shows_the_sign_of_a_negative_nan(capsys: Capture) -> None:
    assert "float: -nan\n" in _run(capsys, "decode", "ffffc000000000000000")[1]


def test_decode_ignores_tabs_and_newlines(capsys: Capture) -> None:
    out = _run(capsys, "decode", "3fff\t8000 0000\n0000 0000", "--json")[1]
    assert json.loads(out)["exact"] == "1"


def test_exponent_beyond_the_decimal_range_is_reported(capsys: Capture) -> None:
    code, _, err = _run(capsys, "encode", "1e999999999999999999999")
    assert code == 1
    assert "too long or large to read" in err


def test_encode_flattened(capsys: Capture) -> None:
    assert _run(capsys, "encode", "1", "--flattened")[1] == "3fff" + "0" * 28 + "\n"
    assert (
        _run(capsys, "encode", "0.1", "--flattened")[1] == "3ffb999999999999999a" + "0" * 12 + "\n"
    )
    little = _run(capsys, "encode", "-2.5", "--flattened", "--byteorder", "little")[1]
    assert little == bytes.fromhex("c0004" + "0" * 27)[::-1].hex() + "\n"


def test_flattened_and_width_cannot_be_combined(capsys: Capture) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["encode", "1", "--flattened", "--width", "16"])
    out, err = capsys.readouterr()
    assert (caught.value.code, out) == (1, "")
    assert "not allowed with argument" in err


def test_decode_flattened_rounds_to_64_bits(capsys: Capture) -> None:
    tie = "3fff" + f"{1 << 48:028x}"
    report = json.loads(_run(capsys, "decode", tie, "--flattened", "--json")[1])
    assert report["mantissa"] == "0x8000000000000000"
    assert report["flattened"] == "3fff" + "0" * 28
    report = json.loads(
        _run(capsys, "decode", tie, "--flattened", "--rounding", "ceiling", "--json")[1]
    )
    assert report["mantissa"] == "0x8000000000000001"


def test_decode_flattened_needs_32_digits(capsys: Capture) -> None:
    code, _, err = _run(capsys, "decode", "3fff8000000000000000", "--flattened")
    assert code == 1
    assert err == "lvext: error: expected 32 hex digits, got 20\n"


def test_decode_reports_the_flattened_form(capsys: Capture) -> None:
    out = _run(capsys, "decode", "3ffbcccccccccccccccd")[1]
    assert out.endswith("flattened: 3ffb999999999999999a000000000000\n")
    out = _run(capsys, "decode", "3fff0000000000000000")[1]
    assert out.endswith("flattened: none (rejected by the 80387 and later)\n")
