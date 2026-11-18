"""Record the example runs that POST /ask serves once the day's spend cap is reached.

Runs the three example questions shown on the /ask page (`ASK_EXAMPLES` in web/lib/copy.ts)
through the live agent on the read-only role and the graph, and writes one file per question
to api/app/ask/replays/. Prints an estimate; sends only with --yes.

    uv run python scripts/record_replays.py          # estimate
    uv run python scripts/record_replays.py --yes    # about $0.01
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COPY_TS = ROOT / "web" / "lib" / "copy.ts"


def examples(path: Path = COPY_TS) -> list[str]:
    """The example questions as the web page shows them, so the replays always match."""
    block = re.search(r"ASK_EXAMPLES = \[(.*?)\];", path.read_text("utf-8"), re.S)
    if block is None:
        raise SystemExit(f"ASK_EXAMPLES not found in {path}")
    return re.findall(r'"([^"]+)"', block.group(1))


def slug(question: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", question.lower())[:5])


def replay(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": run["question"],
        "steps": run["steps"],
        "answer": {
            "text": run["text"],
            "citations": run["citations"],
            "refused": run["refused"],
        },
        "recorded": {k: run[k] for k in ("model", "prompt_version", "cost_usd", "duration_ms")},
    }


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(ROOT))
    from api.app.ask.agent import Agent
    from api.app.ask.service import REPLAY_DIR
    from api.app.ask.tools import Tools
    from api.app.ask.tracing import Tracer
    from api.app.config import get_settings
    from api.app.db import Database
    from api.app.embeddings import Voyage
    from api.app.graph import Graph
    from evals.runners.ask_eval import EST_RUN_USD, VARIANTS, answer_one
    from pipeline.enrich.categories import client_factory

    parser = argparse.ArgumentParser(description="Record the replays served past the cap.")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    args = parser.parse_args(argv)

    questions = examples()
    print(f"{len(questions)} example questions; about ${len(questions) * EST_RUN_USD:.2f} at most.")
    if not args.yes:
        print("Nothing sent. Add --yes to record them.")
        return 0

    settings = get_settings()

    def secret(value: Any) -> str | None:
        return value.get_secret_value() if value else None

    readonly_url = secret(settings.database_url_readonly)
    if not readonly_url:
        raise SystemExit("DATABASE_URL_READONLY is not set: run scripts/create_readonly_role.py.")
    db = Database.open(readonly_url, timeout=settings.db_pool_timeout)
    graph = Graph.open(settings.neo4j_uri, settings.neo4j_user, secret(settings.neo4j_password))
    voyage = Voyage(secret(settings.embeddings_api_key), settings.embeddings_model)
    tracer = Tracer.from_keys(
        settings.langfuse_public_key,
        secret(settings.langfuse_secret_key),
        settings.langfuse_base_url,
    )
    agent = Agent(
        client_factory(),
        settings.model_default,
        settings.embeddings_model,
        tracer,
        tool_names=VARIANTS["agent"],
        name="ask-replay",
    )

    def tools() -> Tools:
        return Tools(contextmanager(db.connection), graph, voyage)

    try:
        REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        for question in questions:
            item = {"id": slug(question), "question": question}
            run = answer_one(item, "agent", agent, tools)
            if run["error"] or not run["text"]:
                raise SystemExit(f"{question!r} failed ({run['error']}); nothing written for it.")
            path = REPLAY_DIR / f"{item['id']}.json"
            path.write_text(json.dumps(replay(run), indent=2, ensure_ascii=False) + "\n",
                            "utf-8", newline="\n")  # fmt: skip
            print(f"{path.name}: {len(run['steps'])} steps, {len(run['citations'])} citations, "
                  f"${run['cost_usd']:.4f}, {run['duration_ms'] / 1000:.1f} s")  # fmt: skip
    finally:
        tracer.flush()
        db.close()
        graph.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
