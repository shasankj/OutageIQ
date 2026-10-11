import { FormEvent, useRef, useState } from "react";
import { ask, sendFeedback, type Final, type HistoryTurn, type Step, type Usage } from "./api";

type Turn = {
  question: string;
  requestId?: string;
  steps: Step[];
  final?: Final;
  usage?: Usage;
  latency?: number;
  error?: string;
  rated?: "up" | "down";
};

const EXAMPLES = [
  "What are the details of outage 1234?",
  "Which outages are still open?",
  "How many outages did each network domain have?",
  "Did outage 9 get a ticket?",
  "Delete all closed tickets.",
];

const STEP_LABELS: Record<string, string> = {
  route: "Understand the question",
  retrieve: "Retrieve schema knowledge",
  generate: "Write SQL",
  validate: "Validate SQL",
  execute: "Run read-only query (MCP)",
  check: "Check the result",
  diagnose: "Diagnose and repair",
  answer: "Write grounded answer",
  respond: "Respond",
  fail: "Give up safely",
  refuse_unsafe: "Refuse unsafe request",
};

function StepList({ steps }: { steps: Step[] }) {
  return (
    <ol className="steps">
      {steps.map((s, i) => (
        <li key={i}>
          <span className="node">{STEP_LABELS[s.node] ?? s.node}</span>
          <span className="ms">{s.ms} ms</span>
          {s.node === "retrieve" && Array.isArray(s.chunks) && (
            <div className="detail">{(s.chunks as string[]).join(" · ")}</div>
          )}
          {s.node === "generate" && typeof s.sql === "string" && <pre className="sql">{s.sql}</pre>}
          {(s.node === "validate" || s.node === "execute") && s.ok === false && (
            <div className="detail bad">
              {String(s.kind)}: {String(s.message)}
            </div>
          )}
          {s.node === "execute" && s.ok === true && <div className="detail">{String(s.rows)} row(s)</div>}
          {s.node === "diagnose" && (
            <div className="detail bad">
              {String(s.kind)} → {String(s.decision)}
            </div>
          )}
          {s.node === "check" && <div className="detail">{String(s.verdict)}</div>}
        </li>
      ))}
    </ol>
  );
}

function Rows({ final }: { final: Final }) {
  if (!final.columns || !final.rows?.length) return null;
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>{final.columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {final.rows.slice(0, 20).map((r, i) => (
            <tr key={i}>{r.map((v, j) => <td key={j}>{v === null ? "NULL" : String(v)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const update = (index: number, patch: Partial<Turn> | ((t: Turn) => Partial<Turn>)) =>
    setTurns((all) =>
      all.map((t, i) => (i === index ? { ...t, ...(typeof patch === "function" ? patch(t) : patch) } : t)),
    );

  async function submit(question: string) {
    if (!question.trim() || busy) return;
    const index = turns.length;
    const history: HistoryTurn[] = turns
      .filter((t) => t.final)
      .slice(-3)
      .map((t) => ({ question: t.question, answer: t.final!.answer, sql: t.final!.sql }));
    setTurns((all) => [...all, { question, steps: [] }]);
    setInput("");
    setBusy(true);
    try {
      await ask(question, history, {
        onStart: (requestId) => update(index, { requestId }),
        onStep: (step) => update(index, (t) => ({ steps: [...t.steps, step] })),
        onFinal: (final, usage, latency) => update(index, { final, usage, latency }),
      });
    } catch (e) {
      update(index, { error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
      setTimeout(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  }

  function rate(index: number, rating: "up" | "down") {
    const turn = turns[index];
    if (!turn.requestId) return;
    void sendFeedback(turn.requestId, rating);
    update(index, { rated: rating });
  }

  return (
    <div className="app">
      <header>
        <h1>OutageIQ</h1>
        <p>Ask questions about outages, tickets, sites and alarms. Answers come only from the data.</p>
      </header>
      <main>
        {turns.length === 0 && (
          <div className="examples">
            {EXAMPLES.map((q) => (
              <button key={q} onClick={() => submit(q)}>
                {q}
              </button>
            ))}
          </div>
        )}
        {turns.map((t, i) => (
          <section key={i} className="turn">
            <div className="q">{t.question}</div>
            {!t.final && !t.error && (
              <div className="working">
                <StepList steps={t.steps} />
                <span className="spinner">working…</span>
              </div>
            )}
            {t.error && <div className="a bad">{t.error}</div>}
            {t.final && (
              <div className={`a ${t.final.kind}`}>
                <div className="answer">{t.final.answer}</div>
                {t.final.warnings?.length ? <div className="detail bad">{t.final.warnings.join("; ")}</div> : null}
                <Rows final={t.final} />
                <div className="actions">
                  <button disabled={!!t.rated} className={t.rated === "up" ? "on" : ""} onClick={() => rate(i, "up")} aria-label="Helpful">
                    👍
                  </button>
                  <button disabled={!!t.rated} className={t.rated === "down" ? "on" : ""} onClick={() => rate(i, "down")} aria-label="Not helpful">
                    👎
                  </button>
                  <span className="meta">
                    {t.final.kind}
                    {t.usage?.cost_usd !== undefined && ` · $${t.usage.cost_usd.toFixed(4)}`}
                    {t.latency !== undefined && ` · ${t.latency.toFixed(1)}s`}
                    {t.final.attempts && t.final.attempts > 1 ? ` · ${t.final.attempts} attempts` : ""}
                  </span>
                </div>
                <details>
                  <summary>How I got this answer</summary>
                  <StepList steps={t.steps} />
                  {t.final.interpretation && <div className="detail">Interpretation: {t.final.interpretation}</div>}
                  {t.final.sql && <pre className="sql">{t.final.sql}</pre>}
                </details>
              </div>
            )}
          </section>
        ))}
        <div ref={bottom} />
      </main>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void submit(input);
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question…" disabled={busy} />
        <button type="submit" disabled={busy || !input.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
