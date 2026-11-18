"""One-time setup for keyless API deploys from GitHub Actions. Prints every command; runs
them only with --yes.

    uv run python scripts/setup_ci_deploy.py --project labellens-api-2611 \\
        --web-origin https://labellens-beige.vercel.app
    uv run python scripts/setup_ci_deploy.py ... --yes

Workload Identity Federation: GitHub's OIDC token for a run on this repository's main branch
is exchanged for a short-lived token of a deploy service account, so no key file exists
anywhere. What it creates:

- a workload identity pool `github` and an OIDC provider `labellens` that accepts tokens only
  from the repository REPO, on refs/heads/main;
- a service account `labellens-deploy` that the provider's tokens may impersonate, with the
  roles to submit Cloud Build, push to Artifact Registry, deploy Cloud Run, list (never read)
  secrets, and act as the runtime account <project number>-compute@developer (which is also
  Cloud Build's default account);
- GitHub repository variables (not secrets: none of these is secret) that
  .github/workflows/deploy-api.yml reads: the project, region, provider, deploy account, web
  origin, API URL, and the plain settings NEO4J_URI, NEO4J_USER, LANGFUSE_PUBLIC_KEY and
  LANGFUSE_BASE_URL. Those come from the environment or .env through api.app.config; their
  values go to `gh` on stdin and are never printed.

Steps that create something fail harmlessly when it already exists, so a rerun is safe.
Run it with gcloud logged in as a project owner and gh logged in with access to REPO.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "adikan2k/labellens"
POOL = "github"
PROVIDER = "labellens"
ACCOUNT = "labellens-deploy"
ISSUER = "https://token.actions.githubusercontent.com"
CONDITION = f"assertion.repository=='{REPO}' && assertion.ref=='refs/heads/main'"
APIS = ["iamcredentials.googleapis.com", "sts.googleapis.com", "iam.googleapis.com"]
# Project-level roles for the deploy account. Each is the narrowest predefined role that
# covers one step of scripts/deploy_api.py --build-and-deploy-only.
PROJECT_ROLES = {
    "roles/cloudbuild.builds.editor": "submit the image build",
    "roles/logging.viewer": "stream the build log (the build logs to Cloud Logging only)",
    "roles/serviceusage.serviceUsageConsumer": "use the project's APIs",
    "roles/run.admin": "deploy Cloud Run and keep it public (--allow-unauthenticated)",
    "roles/secretmanager.viewer": "list secret names to mount; it cannot read a value",
}
PLAIN = ("NEO4J_URI", "NEO4J_USER", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_BASE_URL")


@dataclass(frozen=True)
class Step:
    title: str
    command: list[str]
    stdin: str | None = None  # a repository variable's value: sent, never printed
    may_exist: bool = False  # a create that fails harmlessly on a rerun

    def shown(self) -> str:
        text = shlex.join(self.command)
        return f"{text} < (value from settings)" if self.stdin is not None else text


def account_email(project: str) -> str:
    return f"{ACCOUNT}@{project}.iam.gserviceaccount.com"


def provider_name(project_number: str) -> str:
    return (
        f"projects/{project_number}/locations/global/workloadIdentityPools/{POOL}"
        f"/providers/{PROVIDER}"
    )


def repo_principal(project_number: str) -> str:
    return (
        f"principalSet://iam.googleapis.com/projects/{project_number}/locations/global"
        f"/workloadIdentityPools/{POOL}/attribute.repository/{REPO}"
    )


def variables(
    project: str, project_number: str, region: str, web_origin: str, api_url: str
) -> dict[str, str]:
    """The non-secret repository variables, except the plain settings."""
    return {
        "GCP_PROJECT_ID": project,
        "GCP_REGION": region,
        "GCP_WIF_PROVIDER": provider_name(project_number),
        "GCP_DEPLOY_SA": account_email(project),
        "WEB_ORIGIN": web_origin,
        "API_URL": api_url,
    }


def steps(
    project: str,
    project_number: str,
    region: str,
    web_origin: str,
    api_url: str,
    plain: dict[str, str],
) -> list[Step]:
    email = account_email(project)
    runtime = f"{project_number}-compute@developer.gserviceaccount.com"
    at = f"--project={project}"
    out = [
        Step("Enable the token exchange APIs", ["gcloud", "services", "enable", *APIS, at]),
        Step(
            "Create the workload identity pool",
            ["gcloud", "iam", "workload-identity-pools", "create", POOL, "--location=global",
             "--display-name=GitHub Actions", at],
            may_exist=True,
        ),
        Step(
            f"Create the OIDC provider, limited to {REPO} on main",
            ["gcloud", "iam", "workload-identity-pools", "providers", "create-oidc", PROVIDER,
             "--location=global", f"--workload-identity-pool={POOL}", f"--issuer-uri={ISSUER}",
             "--attribute-mapping=google.subject=assertion.sub,"
             "attribute.repository=assertion.repository,attribute.ref=assertion.ref",
             f"--attribute-condition={CONDITION}", at],
            may_exist=True,
        ),
        Step(
            "Create the deploy service account",
            ["gcloud", "iam", "service-accounts", "create", ACCOUNT,
             "--display-name=LabelLens deploy from GitHub Actions", at],
            may_exist=True,
        ),
        Step(
            f"Let workflows in {REPO} act as the deploy account",
            ["gcloud", "iam", "service-accounts", "add-iam-policy-binding", email,
             "--role=roles/iam.workloadIdentityUser",
             f"--member={repo_principal(project_number)}", at],
        ),
    ]  # fmt: skip
    out += [
        Step(
            f"Grant {role}: {why}",
            ["gcloud", "projects", "add-iam-policy-binding", project,
             f"--member=serviceAccount:{email}", f"--role={role}", "--condition=None"],
        )
        for role, why in PROJECT_ROLES.items()
    ]  # fmt: skip
    out += [
        Step(
            "Let it push images to the labellens repository in Artifact Registry",
            ["gcloud", "artifacts", "repositories", "add-iam-policy-binding", "labellens",
             f"--location={region}", f"--member=serviceAccount:{email}",
             "--role=roles/artifactregistry.writer", at],
        ),
        Step(
            "Let it upload the build source to the Cloud Build bucket",
            ["gcloud", "storage", "buckets", "add-iam-policy-binding",
             f"gs://{project}_cloudbuild", f"--member=serviceAccount:{email}",
             "--role=roles/storage.admin", at],
        ),
        Step(
            "Let it run builds and Cloud Run as the runtime account (actAs, nothing more)",
            ["gcloud", "iam", "service-accounts", "add-iam-policy-binding", runtime,
             f"--member=serviceAccount:{email}", "--role=roles/iam.serviceAccountUser", at],
        ),
    ]  # fmt: skip
    values = variables(project, project_number, region, web_origin, api_url) | plain
    out += [
        Step(
            f"Set the repository variable {name}",
            ["gh", "variable", "set", name, f"--repo={REPO}"],
            stdin=value,
        )
        for name, value in values.items()
        if value
    ]
    return out


def _tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} not found on PATH.")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up keyless deploys from GitHub Actions.")
    parser.add_argument("--project", required=True, help="Google Cloud project id")
    parser.add_argument("--region", default="us-east4")
    parser.add_argument("--web-origin", required=True, help="the Vercel URL")
    parser.add_argument("--api-url", default="", help="the Cloud Run URL, for the smoke test")
    parser.add_argument("--yes", action="store_true", help="run the commands, not just print them")
    args = parser.parse_args(argv)

    gcloud = _tool("gcloud")
    number = subprocess.run(
        [gcloud, "projects", "describe", args.project, "--format=value(projectNumber)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    sys.path.insert(0, str(ROOT))
    from api.app.config import get_settings

    settings = get_settings()
    plain = {name: getattr(settings, name.lower()) or "" for name in PLAIN}
    missing = [name for name, value in plain.items() if not value]
    if missing:
        print(f"Not set in the environment or .env, so left out: {', '.join(missing)}")

    tools = {"gcloud": gcloud, "gh": _tool("gh") if args.yes else "gh"}
    plan = steps(args.project, number, args.region, args.web_origin, args.api_url, plain)
    for step in plan:
        print(f"\n# {step.title}\n{step.shown()}", flush=True)
        if not args.yes:
            continue
        done = subprocess.run(
            [tools[step.command[0]], *step.command[1:]],
            input=step.stdin,
            text=True,
            check=False,
        )
        if done.returncode != 0 and not step.may_exist:
            print(f"Stopped: '{step.title}' failed (exit {done.returncode}).", file=sys.stderr)
            return done.returncode
    if not args.yes:
        print("\nNothing ran. Add --yes to run these commands.")
    else:
        print(
            f"\nDone. Workflows in {REPO} on main can now deploy as {account_email(args.project)}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
