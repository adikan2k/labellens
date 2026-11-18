from pathlib import Path

import pytest

from scripts import deploy_api

ENV_FILE = Path("env.yaml")


def _plan(secrets: dict[str, str] | None = None) -> dict[str, list[str]]:
    return dict(
        deploy_api.commands("my-project", "us-east4", "20261117-1200", "123456", ENV_FILE, secrets)
    )


def test_cloud_run_keeps_the_cost_guardrails() -> None:
    deploy = next(c for title, c in _plan().items() if title.startswith("Deploy"))
    assert "--min-instances=0" in deploy
    assert "--max-instances=2" in deploy
    assert "--allow-unauthenticated" in deploy


def test_secrets_come_from_secret_manager_never_the_command_line() -> None:
    deploy = next(c for title, c in _plan().items() if title.startswith("Deploy"))
    mounted = next(a for a in deploy if a.startswith("--set-secrets="))
    for env, name in deploy_api.SECRETS.items():
        assert f"{env}={name}:latest" in mounted
    joined = " ".join(deploy)
    assert "postgres" not in joined.lower() and "sk-" not in joined
    assert f"--env-vars-file={ENV_FILE}" in deploy


def test_only_existing_secrets_are_mounted_and_granted() -> None:
    plan = _plan({"DATABASE_URL": "labellens-database-url"})
    deploy = next(c for title, c in plan.items() if title.startswith("Deploy"))
    assert "--set-secrets=DATABASE_URL=labellens-database-url:latest" in deploy
    grants = [title for title in plan if title.startswith("Let Cloud Run read")]
    assert grants == ["Let Cloud Run read the secret labellens-database-url"]


def test_ask_fits_in_the_request_timeout() -> None:
    deploy = next(c for title, c in _plan().items() if title.startswith("Deploy"))
    assert "--timeout=60" in deploy  # /ask stops at 45 s


def test_cors_allows_the_web_origin_and_local_dev() -> None:
    assert deploy_api.cors_origins("https://x.vercel.app") == (
        "https://x.vercel.app,http://localhost:3000"
    )
    text = deploy_api.env_file_text(
        {"CORS_ORIGINS": "https://a,http://b", "NEO4J_URI": "", "NEO4J_USER": "neo4j"}
    )
    assert text == 'CORS_ORIGINS: "https://a,http://b"\nNEO4J_USER: "neo4j"\n'


def test_image_is_built_from_the_api_dockerfile_and_tagged() -> None:
    build = next(c for title, c in _plan().items() if title.startswith("Build"))
    assert any(a.endswith("cloudbuild-api.yaml") for a in build)
    image = "us-east4-docker.pkg.dev/my-project/labellens/api:20261117-1200"
    assert f"--substitutions=_IMAGE={image}" in build


def test_registry_keeps_two_images() -> None:
    cleanup = next(c for title, c in _plan().items() if "two newest" in title)
    assert any(a.endswith("artifact-cleanup.json") for a in cleanup)
    policy = (deploy_api.ROOT / "deploy" / "artifact-cleanup.json").read_text("utf-8")
    assert '"keepCount": 2' in policy


def test_runtime_service_account_reads_the_secret() -> None:
    grant = next(c for title, c in _plan().items() if title.startswith("Let Cloud Run read"))
    assert "--member=serviceAccount:123456-compute@developer.gserviceaccount.com" in grant
    assert "--role=roles/secretmanager.secretAccessor" in grant


def test_build_and_deploy_only_skips_the_one_time_steps() -> None:
    full = _plan()
    plan = dict(
        deploy_api.commands(
            "my-project", "us-east4", "20261117-1200", "", ENV_FILE, build_and_deploy_only=True
        )
    )
    assert list(plan) == list(deploy_api.PER_DEPLOY)
    for title in plan:  # the same build and deploy as a full run
        assert plan[title] == full[title]
    skipped = set(full) - set(plan)
    assert "Enable the APIs" in skipped and "Keep only the two newest images" in skipped
    assert not any("add-iam-policy-binding" in c for c in plan.values())


def test_per_deploy_titles_match_the_plan() -> None:
    titles = [title for title, _ in deploy_api.commands("p", "r", "t", "1", ENV_FILE)]
    assert set(deploy_api.PER_DEPLOY) <= set(titles)


def test_build_and_deploy_only_never_describes_the_project(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = "labellens-database-url\nlabellens-neo4j-password\n"

    def fake_run(command: list[str], **kwargs: object) -> Done:
        calls.append(command)
        return Done()

    monkeypatch.setattr(deploy_api, "_gcloud", lambda: "gcloud")
    monkeypatch.setattr(deploy_api.subprocess, "run", fake_run)
    argv = ["--project", "p", "--web-origin", "https://x.vercel.app", "--build-and-deploy-only"]
    assert deploy_api.main(argv) == 0
    assert not any("describe" in c for c in calls)  # the deploy account needs no project read
    assert [c[1:3] for c in calls] == [["secrets", "list"]]  # names only, without --yes
    printed = capsys.readouterr().out
    assert "# Build and push the image" in printed and "# Enable the APIs" not in printed

    calls.clear()
    assert deploy_api.main([*argv, "--yes"]) == 0
    assert [c[1:3] for c in calls] == [["secrets", "list"], ["builds", "submit"], ["run", "deploy"]]
    # The staging bucket is named, so gcloud skips its ownership listing, which would need
    # project-wide storage.buckets.list the deploy account does not have.
    assert "--gcs-source-staging-dir=gs://p_cloudbuild/source" in calls[1]
