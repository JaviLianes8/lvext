"""Every Python example in the README runs and its assertions hold."""

import re
from pathlib import Path

import pytest

_README = Path(__file__).resolve().parents[1] / "README.md"
_BLOCKS = re.findall(r"```python\n(.*?)```", _README.read_text(encoding="utf-8"), re.S)


def test_the_readme_has_python_examples() -> None:
    assert len(_BLOCKS) >= 2


@pytest.mark.parametrize("block", _BLOCKS)
def test_readme_example_runs(block: str) -> None:
    exec(compile(block, str(_README), "exec"), {})
