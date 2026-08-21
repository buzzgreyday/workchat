"""
Measures how often the CV chat denies something the CV actually contains.

A hiring manager asked whether Michael had ever simplified despatch advices and
the app answered that there was no record — while iedi.md describes the redesign
outright. This harness turns that anecdote into a number: it runs a fixed
question set against a live backend, scores every reply, and attributes each
failure to the retrieval step that let it through.

The point is to compare candidate fixes on evidence rather than argument, so the
question set and the scoring are fixed before any of them are tried.

Usage:
  docker compose exec backend python -m tests.evals.run_eval
  docker compose exec backend python -m tests.evals.run_eval --arm granular-resources
  docker compose exec backend python -m tests.evals.run_eval --only 1,6,16   # smoke test

Overrides:
  EVAL_BASE_URL  backend to hit (default: http://localhost:8000)
  ADMIN_KEY      admin key used to mint this run's access token (from the env)

Writes one transcript per run to tests/evals/results/, which is gitignored — the
replies are run artifacts, not source. Each run mints one access token and
leaves one conversation per question in the database.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
QUESTIONS_PATH = EVAL_DIR / "questions.json"
RESULTS_DIR = EVAL_DIR / "results"
BASE_URL = os.environ.get("EVAL_BASE_URL", "http://localhost:8000")

# Phrasings that claim the CV does not cover something. Deliberately anchored to
# CV-absence rather than to negation in general: "did not author raw Helm charts"
# is a scope caveat the prompt asks for, not a denial, and must not score as one.
DENIAL = re.compile(
    r"""
      no\s+(?:specific\s+)?record
    | no\s+records
    | there\s+is\s+no\b
    | there\s+are\s+no\b
    | not\s+mentioned
    | nothing\s+in\s+(?:his|the)\s+cv
    | cv\s+does\s+not\s+(?:mention|cover|include|contain)
    | cv\s+doesn't\s+(?:mention|cover|include|contain)
    | not\s+documented
    | no\s+documented
    | no\s+(?:direct\s+)?evidence
    | no\s+information
    | does\s+not\s+have\s+(?:any\s+)?experience
    | doesn't\s+have\s+(?:any\s+)?experience
    | no\s+experience\s+with
    | has\s+not\s+worked\s+with
    | hasn't\s+worked\s+with
    | not\s+listed
    | (?:isn't|is\s+not)\s+in\s+his\s+cv
    | (?:don't|do\s+not)\s+have\s+that
    | (?:don't|do\s+not|doesn't|does\s+not)\s+have\s+(?:[a-z'’]+\s+){0,3}on\s+file
    | not\s+on\s+file
    | (?:don't|do\s+not|doesn't|does\s+not)\s+have\s+(?:any\s+)?information
    | (?:does\s+not|doesn't|did\s+not|didn't)\s+(?:show|turn\s+up|indicate|include)
    | no\s+mention
    """,
    re.I | re.X,
)


def issue_token(client: httpx.Client, count: int) -> str:
    admin_key = os.environ.get("ADMIN_KEY")
    if not admin_key:
        sys.exit("ADMIN_KEY is not set — run this inside the backend container.")
    resp = client.post(
        "/admin/issue-token",
        headers={"X-Admin-Key": admin_key},
        json={
            "subject": "eval harness",
            "company": "eval",
            "max_queries": count,
            "expires_in_seconds": 3600,
        },
    )
    resp.raise_for_status()
    return resp.json()["token"]


def read_trace(history: list[dict]) -> dict:
    """
    The tool calls behind one reply, each search paired with the count it
    returned. That pairing is what makes a failure attributable.
    """
    searches: list[dict] = []
    fetches: list[str] = []
    pending: dict[str, str] = {}  # tool_call_id -> tool name

    for message in history:
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                pending[call.get("id")] = call.get("function", {}).get("name")
                if call.get("function", {}).get("name") == "get_full_entry":
                    fetches.append(call["function"].get("arguments", ""))
        elif message.get("role") == "tool":
            if pending.get(message.get("tool_call_id")) != "search_cv":
                continue
            try:
                count = json.loads(message.get("content") or "{}").get("count")
            except json.JSONDecodeError:
                count = None
            searches.append({"count": count})

    # Queries are on the assistant side; zip them back on in order.
    queries = [
        call["function"].get("arguments", "")
        for message in history
        if message.get("role") == "assistant"
        for call in message.get("tool_calls") or []
        if call.get("function", {}).get("name") == "search_cv"
    ]
    for search, query in zip(searches, queries):
        search["query"] = query

    return {"searches": searches, "fetches": fetches}


def attribute(trace: dict) -> str:
    """Which step let the failure through."""
    if not trace["searches"]:
        return "no search at all"
    if all(s["count"] == 0 for s in trace["searches"]):
        return "B: every search returned 0"
    if not trace["fetches"]:
        return "A: matched, never fetched"
    return "C: read the entry, still wrong"


def score(question: dict, reply: str) -> tuple[str, str]:
    low = reply.lower()
    # deny_any extends the generic patterns rather than replacing them. As a
    # replacement it scored three correct refusals as failures — "Michael is not
    # part of an on-call rotation" is the right answer and was not in the list.
    denied = bool(DENIAL.search(reply)) or any(d in low for d in question.get("deny_any", []))
    wanted = question.get("must_include_any", [])
    found = [s for s in wanted if s in low]
    expect = question["expect"]

    if expect == "covered":
        if denied:
            return "WRONG NEGATIVE", "claims the CV lacks this"
        if wanted and not found:
            return "MISSED FACT", "no expected detail in the reply"
        return "ok", ""

    if expect == "absent":
        if denied:
            return "ok", ""
        return "WRONG POSITIVE", "never said the CV does not cover it"

    # covered_negative: the CV holds the topic and the true answer is "no".
    if not denied:
        return "WRONG POSITIVE", "did not give the CV's own 'no'"
    if wanted and not found:
        return "MISSED FACT", "denied without naming the topic"
    return "ok", ""


def rescore_saved() -> int:
    """
    Re-score every saved transcript against the current scorer.

    The replies are already paid for. When the scorer changes — and it will, the
    first version graded three correct refusals as failures — past arms have to
    be re-graded on the new rules or the comparison between them is meaningless.
    """
    spec = {q["id"]: q for q in json.loads(QUESTIONS_PATH.read_text())["questions"]}
    for path in sorted(RESULTS_DIR.glob("*.json")):
        run = json.loads(path.read_text())
        tally: dict[str, int] = {}
        for result in run["results"]:
            question = spec.get(result["id"], result)
            verdict, why = score(question, result["reply"])
            if verdict != "ok":
                why = f"{why} [{attribute(result['trace'])}]"
            result["verdict"], result["why"] = verdict, why
            tally[verdict] = tally.get(verdict, 0) + 1
        run["tally"] = tally
        path.write_text(json.dumps(run, indent=2))
        counts = "  ".join(f"{v}: {n}" for v, n in sorted(tally.items()))
        print(f"{path.name:<34} {len(run['results']):>3}q  {counts}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", default="baseline", help="label for this run's results file")
    parser.add_argument("--only", help="comma-separated question ids, for smoke tests")
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="re-grade saved transcripts against the current scorer; makes no API calls",
    )
    args = parser.parse_args()

    if args.rescore:
        return rescore_saved()

    questions = json.loads(QUESTIONS_PATH.read_text())["questions"]
    if args.only:
        wanted = {int(i) for i in args.only.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    if not questions:
        sys.exit("no questions selected")

    try:
        from app.common.config import OPENAI_MODEL as model
    except Exception:  # noqa: BLE001 - the harness must run without app config
        model = "unknown"

    results = []
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        token = issue_token(client, len(questions))
        auth = {"Authorization": f"Bearer {token}"}

        print(f"\narm={args.arm}  model={model}  questions={len(questions)}  {BASE_URL}\n")
        print(f"{'id':>3}  {'probes':<17} {'verdict':<15} why")
        print("-" * 78)

        for question in questions:
            started = time.monotonic()
            resp = client.post("/chat", headers=auth, json={"message": question["question"]})
            resp.raise_for_status()
            body = resp.json()
            reply = body["reply"]

            trace = read_trace(body["history"])
            verdict, why = score(question, reply)
            caveats = question.get("caveat_any")
            caveat_ok = None if not caveats else any(c in reply.lower() for c in caveats)

            if verdict != "ok":
                why = f"{why} [{attribute(trace)}]"
            elif caveat_ok is False:
                why = "passed, but the scope caveat is missing"

            print(f"{question['id']:>3}  {question['probes']:<17} {verdict:<15} {why}")

            results.append(
                {
                    **question,
                    "reply": reply,
                    "verdict": verdict,
                    "why": why,
                    "caveat_ok": caveat_ok,
                    "trace": trace,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )

    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1

    print("-" * 78)
    print("  ".join(f"{verdict}: {n}" for verdict, n in sorted(tally.items())))

    # How often the second hop actually happens. Answering from summaries alone
    # is what the failures had in common, so this is worth watching directly and
    # not only when something has already gone wrong.
    fetched = sum(1 for r in results if r["trace"]["fetches"])
    print(f"fetched a full entry: {fetched}/{len(results)}")

    failures = [r for r in results if r["verdict"] != "ok"]
    if failures:
        paths: dict[str, int] = {}
        for r in failures:
            key = attribute(r["trace"])
            paths[key] = paths.get(key, 0) + 1
        print("failure paths: " + "  ".join(f"{k} ({n})" for k, n in sorted(paths.items())))

    missing_caveats = [r["id"] for r in results if r["caveat_ok"] is False]
    if missing_caveats:
        print(f"scope caveat missing (soft): {missing_caveats}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{args.arm}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(
        json.dumps(
            {"arm": args.arm, "model": model, "tally": tally, "results": results},
            indent=2,
        )
    )
    print(f"\ntranscript: {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
