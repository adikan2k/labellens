"""Deploy the API to Google Cloud Run. Prints every command; runs them only with --yes.

    uv run python scripts/deploy_api.py --project my-project --web-origin https://labellens.vercel.app
    uv run python scripts/deploy_api.py --project my-project --web-origin ... --yes

Before the first run: install the Google Cloud CLI, `gcloud auth login`, and create the
secrets in SECRETS in Secret Manager (at least `labellens-database-url`, Neon's pooled
connection string). This script never sees a secret's value; Cloud Run reads them at start.
Secrets that do not exist yet are left out, and the script says which; without the ask
secrets the API runs and /ask answers 503.

Plain settings (CORS_ORIGINS, NEO4J_URI, NEO4J_USER, LANGFUSE_PUBLIC_KEY, LANGFUSE_BASE_URL) go
in an env-vars file rather than on the command line, where Windows' cmd.exe mangles them.
They come from the environment or .env unless given as flags.

/ask streams for up to 45 seconds, so the request timeout is 60.

Cost guardrails (SPEC section 9): minimum instances 0, maximum 2. Artifact Registry keeps the
two newest images (deploy/artifact-cleanup.json) to stay inside the free 0.5 GB.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "labellens-api"
REPOSITORY = "labellens"
SECRET = "labellens-database-url"
# Environment variable -> Secret Manager secret.
SECRETS = {
    "DATABASE_URL": SECRET,
    "NEO4J_PASSWORD": "labellens-neo4j-password",
    "DATABASE_URL_READONLY": "labellens-database-url-readonly",
    "ANTHROPIC_API_KEY": "labellens-anthropic-key",
    "EMBEDDINGS_API_KEY": "labellens-voyage-key",
    "LANGFUSE_SECRET_KEY": "labellens-langfuse-secret",
}
PLAIN = ("NEO4J_URI", "NEO4J_USER", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_BASE_URL")
APIS = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
]


def image_name(project: str, region: str, tag: str) -> str:
    return f"{region}-docker.pkg.dev/{project}/{REPOSITORY}/api:{tag}"


def cors_origins(web_origin: str) -> str:
    return ",".join([web_origin, "http://localhost:3000"])


def env_file_text(values: dict[str, str]) -> str:
    """A gcloud --env-vars-file (YAML), each value quoted."""
    import json

    return "".join(f"{k}: {json.dumps(v)}\n" for k, v in values.items() if v)


def commands(
    project: str,
    region: str,
    tag: str,
    project_number: str,
    env_file: Path,
    secrets: dict[str, str] | None = None,
) -> list[tuple[str, list[str]]]:
    image = image_name(project, region, tag)
    runtime_account = f"{project_number}-compute@developer.gserviceaccount.com"
    secrets = SECRETS if secrets is None else secrets
    grants = [
        (
            f"Let Cloud Run read the secret {name}",
            [
                "gcloud",
                "secrets",
                "add-iam-policy-binding",
                name,
                f"--member=serviceAccount:{runtime_account}",
                "--role=roles/secretmanager.secretAccessor",
                f"--project={project}",
            ],
        )
        for name in secrets.values()
    ]
    mounted = ",".join(f"{env}={name}:latest" for env, name in secrets.items())
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
        *grants,
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
                "--timeout=60",
                f"--set-secrets={mounted}",
                f"--env-vars-file={env_file}",
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
    for name in PLAIN:
        parser.add_argument(
            f"--{name.lower().replace('_', '-')}", help=f"default: {name} from .env"
        )
    parser.add_argument("--yes", action="store_true", help="run the commands, not just print them")
    args = parser.parse_args(argv)

    gcloud = _gcloud()
    number = subprocess.run(
        [gcloud, "projects", "describe", args.project, "--format=value(projectNumber)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    existing = set(
        subprocess.run(
            [gcloud, "secrets", "list", f"--project={args.project}", "--format=value(name)"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )
    secrets = {env: name for env, name in SECRETS.items() if name in existing}
    if SECRET not in existing:
        raise SystemExit(f"Secret {SECRET} does not exist yet. Create it first (see the top).")
    for env, name in SECRETS.items():
        if name not in existing:
            print(f"Leaving out {env}: secret {name} does not exist yet.")

    sys.path.insert(0, str(ROOT))
    from api.app.config import get_settings

    settings = get_settings()
    plain = {"CORS_ORIGINS": cors_origins(args.web_origin)} | {
        name: getattr(args, name.lower()) or getattr(settings, name.lower()) or "" for name in PLAIN
    }
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / "env.yaml"
        env_file.write_text(env_file_text(plain), "utf-8")
        print(f"Plain settings: {', '.join(k for k, v in plain.items() if v)}")
        plan = commands(args.project, args.region, args.tag, number, env_file, secrets)
        for title, command in plan:
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
