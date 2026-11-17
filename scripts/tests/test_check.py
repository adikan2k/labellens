import io
import sys
from pathlib import Path

from scripts import check

PASS = check.Check("good", "python", (sys.executable, "-c", "print('fine')"))
FAIL = check.Check(
    "bad",
    "python",
    (sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(1)"),
)
MISSING = check.Check("missing", "web", ("definitely-not-a-real-tool-xyz",))


def _run(checks: list[check.Check], tmp_path: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = check.run_checks(checks, cwd=tmp_path, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_all_passing_exits_zero_and_keeps_stderr_empty(tmp_path: Path) -> None:
    code, out, err = _run([PASS, PASS], tmp_path)

    assert code == 0
    assert "All 2 checks passed." in out
    assert err == ""
    assert "fine" not in out  # passing output stays quiet


def test_any_failure_exits_two_with_output_on_stderr(tmp_path: Path) -> None:
    code, out, err = _run([PASS, FAIL], tmp_path)

    assert code == 2
    assert "FAIL  bad" in out
    assert "pass  good" in out
    assert "bad failed" in err
    assert "boom" in err
    assert "fine" not in err


def test_missing_tool_counts_as_failure(tmp_path: Path) -> None:
    code, _, err = _run([MISSING], tmp_path)

    assert code == 2
    assert "not found on PATH" in err


def test_every_check_runs_even_after_a_failure(tmp_path: Path) -> None:
    code, out, _ = _run([FAIL, PASS, FAIL], tmp_path)

    assert code == 2
    assert out.count("FAIL") == 2
    assert "2 of 3 checks failed." in out


def test_only_filters_by_group() -> None:
    groups = {c.group for c in check.CHECKS}
    assert groups == {"python", "web"}
    assert [c.name for c in check.CHECKS if c.group == "web"] == [
        "web lint",
        "web typecheck",
        "web test",
    ]
