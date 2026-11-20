"""Keep the API awake with one Cloud Scheduler job. Prints every command; runs them only with --yes.

    uv run python scripts/keep_warm.py --project my-project
    uv run python scripts/keep_warm.py --project my-project --yes
    uv run python scripts/keep_warm.py --project my-project --remove --yes

Cloud Run runs a minimum of 0 instances (SPEC section 9), and it stops an idle instance after
at most 15 minutes. The next visitor then waits 7 to 10 seconds for a new one
(evals/results/cold_start.md), and the first question waits about 15 more while the ask
agent's libraries load. This job asks for /warm every 5 minutes, so an instance is almost
always up with the agent and the label reader already built. It is not a guarantee: Cloud Run
may still replace an instance, and the first request after a deploy starts a new one.

What it costs: Cloud Scheduler bills per job, not per run, and the first 3 jobs of a billing
account are free ($0.10 a month each after that). The pings are about 8,640 requests a month
of a few milliseconds each, inside Cloud Run's free allowance. Minimum instances stays 0.

/warm runs no database query, so the pings do not keep Neon's compute running. Neon still
pauses after 5 idle minutes and takes about 1 second to wake on the next query. /health is the
wrong address for this: it reads the snapshot date from the database every ten minutes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

SERVICE = "labellens-api"
JOB = "labellens-keep-warm"
API = "cloudscheduler.googleapis.com"
# Well inside the 15 minutes Cloud Run keeps an idle instance, with room for a late run.
SCHEDULE = "*/5 * * * *"
PATH = "/warm"
DESCRIPTION = "Asks the LabelLens API for /warm so an instance stays up with the agent loaded."


def commands(
    project: str, region: str, url: str, *, exists: bool = False, remove: bool = False
) -> list[tuple[str, list[str]]]:
    """Each step as (title, command). `exists`: the job is already there, so update it."""
    where = [f"--location={region}", f"--project={project}"]
    if remove:
        return [
            (
                "Delete the keep-warm job",
                ["gcloud", "scheduler", "jobs", "delete", JOB, *where, "--quiet"],
            )
        ]
    job = [
        "gcloud",
        "scheduler",
        "jobs",
        "update" if exists else "create",
        "http",
        JOB,
        *where,
        f"--schedule={SCHEDULE}",
        "--time-zone=Etc/UTC",
        f"--uri={url.rstrip('/')}{PATH}",
        "--http-method=GET",
        # A new instance takes about 10 s to start and up to 28 s more to build the agent.
        "--attempt-deadline=60s",
        f"--description={DESCRIPTION}",
    ]
    return [
        ("Enable Cloud Scheduler", ["gcloud", "services", "enable", API, f"--project={project}"]),
        (f"{'Update' if exists else 'Create'} the job: {PATH} every 5 minutes", job),
    ]


def _gcloud() -> str:
    found = shutil.which("gcloud")
    if not found:
        raise SystemExit(
            "gcloud not found. Install the Google Cloud CLI and run `gcloud auth login`."
        )
    return found


def _read(gcloud: str, *args: str) -> str:
    """A read-only gcloud call; empty when it fails (an API that is not enabled yet)."""
    done = subprocess.run([gcloud, *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep the API awake with a scheduled ping.")
    parser.add_argument("--project", required=True, help="Google Cloud project id")
    parser.add_argument("--region", default="us-east4", help="where the API runs")
    parser.add_argument("--url", help="the API's address (default: read from Cloud Run)")
    parser.add_argument("--remove", action="store_true", help="delete the job instead")
    parser.add_argument("--yes", action="store_true", help="run the commands, not just print them")
    args = parser.parse_args(argv)

    gcloud = _gcloud()
    where = (f"--region={args.region}", f"--project={args.project}")
    url = args.url or _read(
        gcloud, "run", "services", "describe", SERVICE, *where, "--format=value(status.url)"
    )
    if not url:
        raise SystemExit(f"Could not read the address of {SERVICE}. Pass --url.")

    enabled = _read(
        gcloud,
        "services",
        "list",
        "--enabled",
        f"--project={args.project}",
        f"--filter=config.name:{API}",
        "--format=value(config.name)",
    )
    # Listing jobs on a project without the API would ask to enable it; only look once it is on.
    jobs = (
        _read(
            gcloud,
            "scheduler",
            "jobs",
            "list",
            f"--location={args.region}",
            f"--project={args.project}",
            "--format=value(name)",
        )
        if enabled
        else ""
    )
    exists = any(name.rsplit("/", 1)[-1] == JOB for name in jobs.split())
    if args.remove and not exists:
        print(f"There is no {JOB} job in {args.region}. Nothing to delete.")
        return 0

    print(f"Pings {url.rstrip('/')}{PATH} on the schedule {SCHEDULE} (UTC).")
    print("Cost: the first 3 Cloud Scheduler jobs of a billing account are free.")
    plan = commands(args.project, args.region, url, exists=exists, remove=args.remove)
    for title, command in plan:
        print(f"\n# {title}\n{' '.join(command)}", flush=True)
        if not args.yes:
            continue
        done = subprocess.run([gcloud, *command[1:]], check=False)
        if done.returncode != 0:
            print(f"Stopped: '{title}' failed (exit {done.returncode}).", file=sys.stderr)
            return done.returncode
    if not args.yes:
        print("\nNothing ran. Add --yes to run these commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
