// Mirrors server/relay/schemas.py. Field names are snake_case on the wire.

export type InputKind = "speech" | "keyword" | "typed";
export type Channel = "call" | "voicenote" | "message" | "inperson";
export type ActionType =
  | "send_document"
  | "set_reminder"
  | "send_message"
  | "place_call"
  | "order"
  | "none";
export type EngineSource = "bedrock" | "anthropic" | "openai" | "groq" | "scripted";

export interface InputSignal {
  kind: InputKind;
  text: string;
  at: number;
}

export interface Turn {
  speaker: "user" | "partner";
  text: string;
  at: number;
}

export interface Partner {
  name: string;
  role: string;
  relationship: string;
}

export interface ActionSpec {
  type: ActionType;
  summary: string;
  params: Record<string, string>;
}

export interface Candidate {
  id: string;
  text: string;
  gist: string;
  confidence: number;
  action: ActionSpec | null;
}

export interface PredictRequest {
  signals: InputSignal[];
  channel: Channel;
  partner?: Partner;
  transcript?: Turn[];
  count?: number;
}

export interface PredictResponse {
  candidates: Candidate[];
  latency_ms: number;
  source: EngineSource;
  degraded: boolean;
}

export interface Scenario {
  id: string;
  title: string;
  blurb: string;
  partner: Partner;
  goal: string;
  opening: string;
}

export interface CallReplyResponse {
  text: string;
  ended: boolean;
  source: EngineSource;
}

export interface CommitResponse {
  spoken: string;
  receipt: string;
  source: EngineSource;
}

export interface Health {
  provider: EngineSource;
  fast_model: string;
  smart_model: string;
  memory_backend: string;
  scripted_fallback: boolean;
}

export interface ActivityEntry {
  kind: string;
  detail: string;
  at: number;
}

export interface Activity {
  entries: ActivityEntry[];
  memory: { backend: string; recorded: number };
}

export const CHANNEL_LABELS: Record<Channel, string> = {
  call: "On a call",
  voicenote: "Voice note",
  message: "Message",
  inperson: "In person",
};
