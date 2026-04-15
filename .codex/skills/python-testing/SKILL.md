---
name: python-testing
description: Python testing strategies for Codex sessions, with framework-aware guidance for unittest and pytest, plus TDD and coverage practices.
origin: codex-adapted
---

# Python Testing Patterns

Framework-aware testing guidance for Python projects.

## When to Activate

- Adding or changing Python behavior
- Fixing bugs with regression tests
- Expanding test coverage
- Reviewing test quality and reliability

## First Rule: Match the Existing Test Stack

Before writing tests:

1. Detect the existing framework in repo.
- If tests use `unittest`, continue with `unittest`.
- If tests use `pytest`, continue with `pytest`.

2. Use the repo's existing test command when available.

For this repository, default command is:

```bash
python3 -m unittest tests.test_ssl_monitor tests.test_monthly_uptime_report -v
```

## Testing Workflow (Preferred)

1. Reproduce behavior with a failing test.
2. Implement minimal code to pass.
3. Refactor safely with tests green.
4. Run focused tests first, then broader suite when needed.

## unittest Patterns

### Basic test class

```python
import unittest


class TestMath(unittest.TestCase):
    def test_add(self) -> None:
        self.assertEqual(2 + 3, 5)


if __name__ == "__main__":
    unittest.main()
```

### setUp/tearDown

```python
import tempfile
import unittest
from pathlib import Path


class TestFileIO(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "sample.txt"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_write_read(self) -> None:
        self.path.write_text("hello", encoding="utf-8")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "hello")
```

### Mocking

```python
from unittest.mock import patch
import unittest


def fetch_data() -> str:
    import requests
    return requests.get("https://example.com").text


class TestFetch(unittest.TestCase):
    @patch("requests.get")
    def test_fetch_data(self, mock_get) -> None:
        mock_get.return_value.text = "ok"
        self.assertEqual(fetch_data(), "ok")
```

## pytest Patterns (when repo uses pytest)

```python
import pytest


@pytest.mark.parametrize("a,b,expected", [(1, 2, 3), (2, 5, 7)])
def test_add(a, b, expected):
    assert a + b == expected
```

## What to Test

- Happy path behavior
- Edge cases and invalid input
- Error handling and exception paths
- Regression cases for fixed bugs

## Good Test Qualities

- Deterministic (no flaky timing/network dependence)
- Isolated (no shared mutable state)
- Focused (one behavior per test)
- Readable names (`test_<behavior>_<expected_result>`)

## Coverage Guidance

- Prioritize meaningful coverage over raw percentage.
- Ensure critical paths are tested.
- If coverage tooling exists, report results; do not add tooling unless requested.

## Validation Strategy

Run smallest relevant subset first, then expand:

1. Targeted module tests
2. Related suite
3. Full suite (if needed for confidence)

If tests cannot be run, state why and what remains unverified.
