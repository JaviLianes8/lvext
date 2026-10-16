"""Every Python example and command line transcript in README and GUIDE holds."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lvext._cli import main

ROOT = Path(__file__).resolve().parents[1]
DOCS = {name: (ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "GUIDE.md")}
PYTHON = [
    (n, b) for n, text in DOCS.items() for b in re.findall(r"```python\n(.*?)```", text, re.S)
]
CONSOLE = [
    (n, b) for n, text in DOCS.items() for b in re.findall(r"```console\n(.*?)```", text, re.S)
]


def test_both_documents_have_examples() -> None:
    assert {n for n, _ in PYTHON} == {n for n, _ in CONSOLE} == set(DOCS)


@pytest.mark.parametrize(("name", "block"), PYTHON)
def test_python_example_runs(name: str, block: str) -> None:
    exec(compile(block, name, "exec"), {})


@pytest.mark.parametrize(("name", "block"), CONSOLE)
def test_console_transcript_matches(
    name: str, block: str, capsys: pytest.CaptureFixture[str]
) -> None:
    commands = re.split(r"^\$ lvext ", block, flags=re.M)[1:]
    assert commands, name
    for command in commands:
        line, _, expected = command.partition("\n")
        assert main(line.split()) == 0
        assert capsys.readouterr().out == expected


@pytest.mark.parametrize("name", list(DOCS))
def test_links_are_absolute_and_text_is_plain(name: str) -> None:
    text = DOCS[name]
    for target in re.findall(r"\]\(([^)]+)\)", text):
        assert target.startswith("https://"), target
    assert chr(0x2014) not in text


def test_the_guide_names_every_public_name() -> None:
    import lvext

    for public in lvext.__all__:
        assert f"`{public}" in DOCS["GUIDE.md"], public
