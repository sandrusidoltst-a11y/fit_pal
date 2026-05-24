"""Runner for the hebrew-friend-coach-tone UX loop.

Drives the 7 scenarios from inputs/scenarios.md against a local langgraph
dev server at http://127.0.0.1:2024. Saves per-scenario transcripts as
JSON to a caller-specified output directory.

**Important:** loads `user_profile` from Supabase and injects it into the
runtime context, matching what `bot/gateway.py:_load_user_profile`
does in production. Without this, the graph falls back to
`DEFAULT_DEV_PROFILE` in `src/context.py` (a hardcoded fake plan), which
produces correct-looking but content-wrong replies. This was the F1
root cause in run2-after-seed.

Usage:
    uv run python tests/ux-loop/hebrew-friend-coach-tone/runner.py <output_dir>

The langgraph dev server must already be running. Start it with:
    uv run langgraph dev --port 2024 --no-browser

Future improvement: parse inputs/scenarios.md instead of hardcoding the
7 turns below.
"""
import asyncio
import json
import sys
from pathlib import Path

import asyncpg
from langgraph_sdk import get_client

REPO_ROOT = Path(__file__).resolve().parents[3]

# Load .env without dotenv (avoids assertion issue with inline scripts)
_env: dict[str, str] = {}
for _line in (REPO_ROOT / ".env").read_text().splitlines():
    if "=" in _line and not _line.strip().startswith("#"):
        _k, _, _v = _line.partition("=")
        _env[_k.strip()] = _v.strip().strip('"').strip("'")

USER_ID = "72c10336-9d61-4357-9851-20cbb4d32b1a"  # e2e@test.fitpal.bot — same as tests/graph_api/


SCENARIOS = [
    {
        "id": 1, "slug": "empty-day-greeting",
        "turns": [{"text": "היי", "expect": "final"}],
    },
    {
        "id": 2, "slug": "normal-log-tight-confirmation",
        "turns": [{"text": "אכלתי 200 גרם עוף", "expect": "interrupt", "resume": "כן"}],
    },
    {
        "id": 3, "slug": "off-menu-plan-deviation",
        "turns": [{"text": "דפקתי עכשיו לאפה שווארמה", "expect": "interrupt", "resume": "כן"}],
    },
    {
        "id": 4, "slug": "daily-stats-time-pacing",
        "turns": [{"text": "מה מצבי להיום?", "expect": "final"}],
    },
    {
        "id": 5, "slug": "unit-mismatch-coach-retry",
        "turns": [{"text": "אכלתי כוס ביצים", "expect": "final"}],
    },
    {
        "id": 6, "slug": "food-info-qna",
        "turns": [{"text": "תגיד, כמה פחמימה יש באורז?", "expect": "final"}],
    },
    {
        "id": 7, "slug": "weekly-synthesis",
        "turns": [{"text": "מה אכלתי השבוע?", "expect": "final"}],
    },
]


async def load_profile() -> dict:
    """Mirror bot/gateway.py:_load_user_profile — fetch profile from DB."""
    conn = await asyncpg.connect(_env["SUPABASE_DB_URL"], ssl="require")
    row = await conn.fetchrow(
        "SELECT name, age, gender, height_cm, nutrition_plan "
        "FROM user_profiles WHERE user_id = $1",
        USER_ID,
    )
    await conn.close()
    if not row:
        raise RuntimeError(
            f"No user_profiles row for {USER_ID}. Seed one before running "
            f"(see runs/run2-after-seed/db-snapshot.md for the seed pattern)."
        )
    return {
        "name": row["name"],
        "age": row["age"],
        "gender": row["gender"],
        "height_cm": row["height_cm"],
        "nutrition_plan": row["nutrition_plan"],
    }


def _last_ai(final: dict | None) -> str | None:
    for m in reversed((final or {}).get("messages") or []):
        if m.get("type") == "ai":
            return m.get("content", "")
    return None


async def _get_interrupt(client, thread_id: str):
    state = await client.threads.get_state(thread_id)
    interrupts = [
        it.get("value")
        for t in (state.get("tasks") or [])
        for it in (t.get("interrupts") or [])
    ]
    return interrupts[0] if interrupts else None


async def run_scenario(client, ctx: dict, scen: dict) -> dict:
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    transcript = {"id": scen["id"], "slug": scen["slug"], "thread_id": thread_id, "turns": []}

    final = None
    for turn in scen["turns"]:
        async for chunk in client.runs.stream(
            thread_id, "fitpal",
            input={"messages": [{"role": "user", "content": turn["text"]}]},
            context=ctx, stream_mode="values",
        ):
            if chunk.event == "values":
                final = chunk.data

        interrupt_value = await _get_interrupt(client, thread_id)
        turn_log = {
            "user": turn["text"],
            "expected": turn["expect"],
            "got": "interrupt" if interrupt_value else "final",
        }
        if interrupt_value:
            turn_log["interrupt_value"] = interrupt_value
        else:
            turn_log["ai_reply"] = _last_ai(final)
        transcript["turns"].append(turn_log)

        if turn.get("resume") and interrupt_value:
            resume_text = turn["resume"]
            async for chunk in client.runs.stream(
                thread_id, "fitpal",
                command={"resume": resume_text},
                context=ctx, stream_mode="values",
            ):
                if chunk.event == "values":
                    final = chunk.data
            after = await _get_interrupt(client, thread_id)
            transcript["turns"].append({
                "resume": resume_text,
                "got": "interrupt" if after else "final",
                "interrupt_value": after if after else None,
                "ai_reply": _last_ai(final) if not after else None,
            })

    return transcript


async def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = await load_profile()
    print(f"=== profile loaded: name={profile['name']}, plan_chars={len(profile['nutrition_plan'])} ===")
    ctx = {"user_id": USER_ID, "user_profile": profile}

    client = get_client(url="http://127.0.0.1:2024")
    results = []
    for scen in SCENARIOS:
        print(f"\n=== Scenario {scen['id']}: {scen['slug']} ===")
        try:
            t = await run_scenario(client, ctx, scen)
            results.append(t)
            (out_dir / f"scenario_{scen['id']:02d}_{scen['slug']}.json").write_text(
                json.dumps(t, ensure_ascii=False, indent=2)
            )
            for turn in t["turns"]:
                if "user" in turn:
                    print(f"  USER: {turn['user']}  -> expected={turn['expected']} got={turn['got']}")
                elif "resume" in turn:
                    print(f"  RESUME: {turn['resume']}  -> got={turn['got']}")
                if turn.get("ai_reply"):
                    reply = turn["ai_reply"][:200].replace("\n", " | ")
                    print(f"     AI: {reply}{'...' if len(turn.get('ai_reply','')) > 200 else ''}")
                if turn.get("interrupt_value"):
                    q = (turn["interrupt_value"].get("question") or "")[:120]
                    print(f"     INT.question: {q}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            results.append({"id": scen["id"], "slug": scen["slug"], "error": str(e)})

    (out_dir / "all_scenarios.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2)
    )
    print(f"\n=== DONE. Saved {len(results)} scenarios to {out_dir} ===")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: runner.py <output_dir>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(Path(sys.argv[1])))
