from scripts import setup_ci_deploy as setup

PLAIN = {
    "NEO4J_URI": "neo4j+s://abc.databases.neo4j.io",
    "NEO4J_USER": "neo4j",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-123",
    "LANGFUSE_BASE_URL": "",
}


def _steps() -> list[setup.Step]:
    return setup.steps(
        "my-project", "123456", "us-east4", "https://x.vercel.app", "https://api.run.app", PLAIN
    )


def _find(start: str) -> setup.Step:
    return next(s for s in _steps() if s.title.startswith(start))


def test_the_provider_only_accepts_this_repository_on_main() -> None:
    provider = _find("Create the OIDC provider").command
    assert "--issuer-uri=https://token.actions.githubusercontent.com" in provider
    condition = next(a for a in provider if a.startswith("--attribute-condition="))
    assert "assertion.repository=='adikan2k/labellens'" in condition
    assert "assertion.ref=='refs/heads/main'" in condition
    binding = _find("Let workflows in").command
    assert "--role=roles/iam.workloadIdentityUser" in binding
    member = next(a for a in binding if a.startswith("--member="))
    assert member.endswith("/workloadIdentityPools/github/attribute.repository/adikan2k/labellens")
    assert "projects/123456/" in member


def test_the_deploy_account_gets_exactly_the_roles_to_build_and_deploy() -> None:
    granted = {
        next(a for a in s.command if a.startswith("--role="))[len("--role=") :]
        for s in _steps()
        if "add-iam-policy-binding" in s.command and "Let workflows" not in s.title
    }
    assert granted == {
        "roles/cloudbuild.builds.editor",
        "roles/logging.viewer",
        "roles/serviceusage.serviceUsageConsumer",
        "roles/run.admin",
        "roles/secretmanager.viewer",
        "roles/artifactregistry.writer",
        "roles/storage.admin",
        "roles/iam.serviceAccountUser",
    }
    assert not any("owner" in r or r.split("/")[-1] == "editor" for r in granted)
    assert "roles/secretmanager.secretAccessor" not in granted  # lists names, reads no value


def test_storage_and_act_as_are_scoped_to_one_resource() -> None:
    bucket = _find("Let it upload").command
    assert "gs://my-project_cloudbuild" in bucket and "buckets" in bucket
    act_as = _find("Let it run builds").command
    assert act_as[4] == "123456-compute@developer.gserviceaccount.com"
    push = _find("Let it push").command
    assert "repositories" in push and "labellens" in push


def test_repository_variables_go_on_stdin_and_are_never_printed() -> None:
    variables = {s.command[3]: s for s in _steps() if s.command[:3] == ["gh", "variable", "set"]}
    assert set(variables) == {
        "GCP_PROJECT_ID",
        "GCP_REGION",
        "GCP_WIF_PROVIDER",
        "GCP_DEPLOY_SA",
        "WEB_ORIGIN",
        "API_URL",
        "NEO4J_URI",
        "NEO4J_USER",
        "LANGFUSE_PUBLIC_KEY",
    }  # LANGFUSE_BASE_URL is empty, so it is left out
    assert variables["NEO4J_URI"].stdin == PLAIN["NEO4J_URI"]
    assert variables["GCP_WIF_PROVIDER"].stdin == (
        "projects/123456/locations/global/workloadIdentityPools/github/providers/labellens"
    )
    assert variables["GCP_DEPLOY_SA"].stdin == "labellens-deploy@my-project.iam.gserviceaccount.com"
    for step in variables.values():
        assert "--repo=adikan2k/labellens" in step.command
        assert step.stdin is not None and step.stdin not in step.shown()


def test_creates_tolerate_a_rerun_but_grants_do_not() -> None:
    for step in _steps():
        creates = "create" in step.command or "create-oidc" in step.command
        assert step.may_exist == creates, step.title


def test_the_secret_settings_are_never_variables() -> None:
    names = " ".join(" ".join(s.command) for s in _steps())
    for secret in ("NEO4J_PASSWORD", "DATABASE_URL", "ANTHROPIC_API_KEY", "LANGFUSE_SECRET_KEY"):
        assert secret not in names
