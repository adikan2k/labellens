"""Deploy the API to Google Cloud Run. Prints every command; runs them only with --yes.

    uv run python scripts/deploy_api.py --project my-project --web-origin https://labellens.vercel.app
    uv run python scripts/deploy_api.py --project my-project --web-origin ... --yes

Before the first run: install the Google Cloud CLI, `gcloud auth login`, and create the secret
`labellens-database-url` in Secret Manager holding Neon's pooled connection string. This script
never sees the secret's value; Cloud Run reads it at start.

Cost guardrails (SPEC section 9): minimum instances 0, maximum 2. Artifact Registry keeps the
two newest images (deploy/artifact-cleanup.json) to stay inside the free 0.5 GB.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "labellens-api"
REPOSITORY = "labellens"
SECRET = "labellens-database-url"
APIS = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
]


def image_name(project: str, region: str, tag: str) -> str:
    return f"{region}-docker.pkg.dev/{project}/{REPOSITORY}/api:{tag}"


def commands(
    project: str, region: str, tag: str, web_origin: str, project_number: str
) -> list[tuple[str, list[str]]]:
    image = image_name(project, region, tag)
    runtime_account = f"{project_number}-compute@developer.gserviceaccount.com"
    origins = ",".join([web_origin, "http://localhost:3000"])
    return [
        ("Enable the APIs", ["gcloud", "services", "enable", *APIS, f"--project={project}"]),
        (
            "Create the image repository (fails harmlessly if it exists)",
            [
                "gcloud",
                "artifacts",
                "repositories",
                "create",
                REPOSITORY,
                "--repository-format=docker",
                f"--location={region}",
                f"--project={project}",
            ],
        ),
        (
            "Keep only the two newest images",
            [
                "gcloud",
                "artifacts",
                "repositories",
                "set-cleanup-policies",
                REPOSITORY,
                f"--location={region}",
                f"--project={project}",
                f"--policy={ROOT / 'deploy' / 'artifact-cleanup.json'}",
                "--no-dry-run",
            ],
        ),
        (
            "Let Cloud Run read the database secret",
            [
                "gcloud",
                "secrets",
                "add-iam-policy-binding",
                SECRET,
                f"--member=serviceAccount:{runtime_account}",
                "--role=roles/secretmanager.secretAccessor",
                f"--project={project}",
            ],
        ),
        (
            "Build and push the image",
            [
                "gcloud",
                "builds",
                "submit",
                str(ROOT),
                f"--config={ROOT / 'deploy' / 'cloudbuild-api.yaml'}",
                f"--substitutions=_IMAGE={image}",
                f"--project={project}",
            ],
        ),
        (
            "Deploy to Cloud Run (public, read-only API)",
            [
                "gcloud",
                "run",
                "deploy",
                SERVICE,
                f"--image={image}",
                f"--region={region}",
                f"--project={project}",
                "--allow-unauthenticated",
                "--min-instances=0",
                "--max-instances=2",
                "--cpu=1",
                "--memory=512Mi",
                "--concurrency=40",
                "--timeout=30",
                f"--set-secrets=DATABASE_URL={SECRET}:latest",
                f"--set-env-vars=^@^CORS_ORIGINS={origins}",
            ],
        ),
    ]


def _gcloud() -> str:
    found = shutil.which("gcloud")
    if not found:
        raise SystemExit(
            "gcloud not found. Install the Google Cloud CLI and run `gcloud auth login`."
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy the API to Cloud Run.")
    parser.add_argument("--project", required=True, help="Google Cloud project id")
    parser.add_argument("--region", default="us-east4", help="near Neon's AWS us-east-1")
    parser.add_argument("--web-origin", required=True, help="the Vercel URL, for CORS")
    parser.add_argument("--tag", default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--yes", action="store_true", help="run the commands, not just print them")
    args = parser.parse_args(argv)

    gcloud = _gcloud()
    number = subprocess.run(
        [gcloud, "projects", "describe", args.project, "--format=value(projectNumber)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    for title, command in commands(args.project, args.region, args.tag, args.web_origin, number):
        print(f"\n# {title}\n{' '.join(command)}", flush=True)
        if not args.yes:
            continue
        done = subprocess.run([gcloud, *command[1:]], check=False)
        if done.returncode != 0 and "repositories create" not in " ".join(command):
            print(f"Stopped: '{title}' failed (exit {done.returncode}).", file=sys.stderr)
            return done.returncode
    if not args.yes:
        print("\nNothing ran. Add --yes to run these commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
