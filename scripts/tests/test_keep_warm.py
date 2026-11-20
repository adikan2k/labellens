import pytest

from scripts import keep_warm

URL = "https://labellens-api-123.us-east4.run.app"


def _plan(**kwargs: bool) -> dict[str, list[str]]:
    return dict(keep_warm.commands("my-project", "us-east4", URL, **kwargs))


def test_the_job_asks_for_warm_every_five_minutes() -> None:
    job = next(c for title, c in _plan().items() if title.startswith("Create"))
    assert job[:5] == ["gcloud", "scheduler", "jobs", "create", "http"]
    assert keep_warm.JOB in job
    assert "--schedule=*/5 * * * *" in job
    assert f"--uri={URL}/warm" in job
    assert "--http-method=GET" in job
    assert "--location=us-east4" in job and "--project=my-project" in job


def test_the_ping_is_well_inside_cloud_runs_idle_window() -> None:
    # Cloud Run keeps an idle instance for at most 15 minutes.
    minutes = int(keep_warm.SCHEDULE.split()[0].removeprefix("*/"))
    assert minutes * 2 < 15


def test_the_ping_goes_to_the_address_that_skips_the_database() -> None:
    # /warm runs no query (api/tests/test_health.py); /health reads the snapshot date.
    job = next(c for title, c in _plan().items() if title.startswith("Create"))
    uri = next(a for a in job if a.startswith("--uri="))
    assert uri.endswith("/warm")


def test_the_ping_waits_long_enough_for_a_new_instance_to_build_the_agent() -> None:
    job = next(c for title, c in _plan().items() if title.startswith("Create"))
    assert "--attempt-deadline=60s" in job


def test_a_trailing_slash_on_the_address_does_not_double_up() -> None:
    plan = dict(keep_warm.commands("p", "us-east4", URL + "/"))
    job = next(c for title, c in plan.items() if title.startswith("Create"))
    assert f"--uri={URL}/warm" in job


def test_the_api_is_enabled_before_the_job_is_made() -> None:
    titles = list(_plan())
    assert titles[0] == "Enable Cloud Scheduler"
    assert titles[1].startswith("Create")


def test_an_existing_job_is_updated_not_created_again() -> None:
    job = next(c for title, c in _plan(exists=True).items() if title.startswith("Update"))
    assert job[:5] == ["gcloud", "scheduler", "jobs", "update", "http"]


def test_remove_deletes_only_the_job() -> None:
    plan = _plan(remove=True)
    assert list(plan) == ["Delete the keep-warm job"]
    (command,) = plan.values()
    assert command[:4] == ["gcloud", "scheduler", "jobs", "delete"]
    assert keep_warm.JOB in command and "--quiet" in command


def test_nothing_runs_without_yes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = ""

    def fake_run(command: list[str], **_: object) -> Done:
        ran.append(command)
        return Done()

    monkeypatch.setattr(keep_warm, "_gcloud", lambda: "gcloud")
    monkeypatch.setattr(keep_warm.subprocess, "run", fake_run)
    assert keep_warm.main(["--project", "my-project", "--url", URL]) == 0
    out = capsys.readouterr().out
    assert "Nothing ran. Add --yes" in out
    assert "jobs create http" in out
    # Only read-only calls: which services are enabled.
    assert all("create" not in c and "enable" not in c for c in ran)
