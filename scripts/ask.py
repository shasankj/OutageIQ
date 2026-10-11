"""Ask the agent one question and print the whole run: Run: python -m scripts.ask "Which outages are still open?"

Shows each node (the LangGraph trace), the SQL, every repair attempt, the answer, tokens, cost and latency.
"""
import asyncio
import json
import sys

from agent.runner import create_agent


async def main(question: str) -> int:
    async with create_agent() as agent:
        result = await agent.ask(question)
    print(f"\nQ: {question}\n\n== trace ==")
    for e in result["events"]:
        extra = {k: v for k, v in e.items() if k not in ("node", "ms")}
        print(f"{e['node']:<14}{e['ms']:>6} ms  {json.dumps(extra, default=str)[:260]}")
    for a in result["attempts"]:
        print(f"\nfailed attempt {a['n']}: {a['outcome']}\n  {a['sql']}")
    final = result["final"]
    print(f"\n== result: {final['kind']} ==")
    if final.get("sql"):
        print(final["sql"])
    print(f"\n{final['answer']}\n")
    print(f"usage: {result['usage']}  latency: {result['latency_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(" ".join(sys.argv[1:]) or "What are the details of outage 1234?")))
