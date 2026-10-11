export type Step = {
  node: string;
  ms: number;
  [key: string]: unknown;
};

export type Usage = { llm_calls?: number; input_tokens?: number; output_tokens?: number; cost_usd?: number };

export type Final = {
  kind: string;
  answer: string;
  sql?: string | null;
  interpretation?: string | null;
  columns?: string[];
  rows?: unknown[][];
  row_count?: number;
  attempts?: number;
  warnings?: string[];
  grounded?: boolean;
};

export type AskEvents = {
  onStart: (requestId: string) => void;
  onStep: (step: Step) => void;
  onFinal: (final: Final, usage: Usage, latency: number) => void;
};

/** POST /ask and read the server-sent events (EventSource cannot POST, so parse the stream by hand). */
export type HistoryTurn = { question: string; answer: string; sql?: string | null };

export async function ask(question: string, history: HistoryTurn[], handlers: AskEvents): Promise<void> {
  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!response.ok || !response.body) throw new Error(`Request failed (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "start") handlers.onStart(payload.request_id);
      else if (event === "step") handlers.onStep(payload as Step);
      else if (event === "final") handlers.onFinal(payload.final, payload.usage, payload.latency_s);
    }
  }
}

export async function sendFeedback(requestId: string, rating: "up" | "down"): Promise<void> {
  await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, rating }),
  });
}
