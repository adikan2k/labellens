from scripts import deploy_api


def _plan() -> dict[str, list[str]]:
    return dict(
        deploy_api.commands(
            "my-project", "us-east4", "20261117-1200", "https://labellens.vercel.app", "123456"
        )
    )


def test_cloud_run_keeps_the_cost_guardrails() -> None:
    deploy = next(c for title, c in _plan().items() if title.startswith("Deploy"))
    assert "--min-instances=0" in deploy
    assert "--max-instances=2" in deploy
    assert "--allow-unauthenticated" in deploy


def test_database_url_comes_from_secret_manager_never_the_command_line() -> None:
    deploy = next(c for title, c in _plan().items() if title.startswith("Deploy"))
    joined = " ".join(deploy)
    assert "--set-secrets=DATABASE_URL=labellens-database-url:latest" in joined
    assert "postgres" not in joined.lower()


def test_cors_allows_the_web_origin_and_local_dev() -> None:
    deploy = next(c for title, c in _plan().items() if title.startswith("Deploy"))
    env = next(a for a in deploy if a.startswith("--set-env-vars="))
    assert "https://labellens.vercel.app,http://localhost:3000" in env


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
    grant = next(c for title, c in _plan().items() if "secret" in title)
    assert "--member=serviceAccount:123456-compute@developer.gserviceaccount.com" in grant
    assert "--role=roles/secretmanager.secretAccessor" in grant
