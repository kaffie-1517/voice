import type {
  Activity,
  CallReplyResponse,
  Channel,
  ActionSpec,
  CommitResponse,
  Health,
  PredictRequest,
  PredictResponse,
  Scenario,
  Turn,
} from "./types";

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/api/health"),
  scenarios: () => get<Scenario[]>("/api/scenarios"),
  activity: () => get<Activity>("/api/activity"),
  predict: (req: PredictRequest, signal?: AbortSignal) =>
    post<PredictResponse>("/api/predict", req, signal),
  partnerReply: (scenario_id: string, transcript: Turn[]) =>
    post<CallReplyResponse>("/api/call/reply", { scenario_id, transcript }),
  commit: (text: string, channel: Channel, action: ActionSpec | null) =>
    post<CommitResponse>("/api/commit", { text, channel, action }),
};
