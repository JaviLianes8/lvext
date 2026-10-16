# Contributing

Thanks for taking the time. This project keeps a small, predictable shape.

## Setup

From a clone of the repository (the source distribution does not ship the dev files):

```
pip install -e . -r requirements-dev.txt
```

## Before you open a pull request

- Keep public API in `src/lvext/__init__.py`; internals live in `_`-prefixed modules.
- Add a test for the behaviour you change. Unit tests are pure. The end-to-end test
  installs the package into a throwaway virtual environment, and the hardware test
  compares results with the x87 FPU on Windows x86-64 (it skips elsewhere).
- Run `scripts/check.ps1` (format, lint, types, tests) and make sure it passes.
- One logical change per commit, imperative subject line.

Open an issue first if the change is large or shifts the public API.
