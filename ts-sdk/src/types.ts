export type ArtifactKind =
  | "llm.prompt"
  | "llm.response"
  | "tool.input"
  | "tool.output"
  | "file.diff"
  | "command.stdout"
  | "command.stderr";

export interface RunRecord {
  id: string;
  project_id: string;
  organization_id?: string | null;
  workflow_name: string;
  agent_name: string;
  status: "running" | "success" | "failed";
  started_at: string;
  ended_at: string | null;
  total_input_tokens?: number;
  total_output_tokens?: number;
  total_tokens?: number;
  total_cost_usd?: number;
}

export interface SpanRecord {
  id: string;
  run_id: string;
  parent_span_id: string | null;
  span_type: string;
  name: string;
  status: "running" | "success" | "failed";
  started_at: string;
  ended_at: string | null;
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  estimated_cost?: number | null;
  context_window?: number | null;
  context_usage_percent?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface ArtifactRecord {
  id: string;
  run_id: string;
  span_id: string | null;
  kind: ArtifactKind;
  payload: unknown;
}

export interface IngestPayload {
  run: RunRecord;
  spans: SpanRecord[];
  artifacts: ArtifactRecord[];
}

export interface AgentScopeClientOptions {
  baseUrl?: string;
  apiKey?: string;
  timeoutMs?: number;
}

export interface ObserveRunOptions {
  agentName?: string;
  projectId?: string;
  exporter?: TelemetryExporterLike;
}

export interface ObserveSpanOptions {
  spanType?: string;
  metadata?: Record<string, unknown>;
  provider?: string;
  model?: string;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  estimatedCost?: number;
  contextWindow?: number;
  contextUsagePercent?: number;
}

export interface FetchInstrumentationOptions {
  spanName?: string;
  ignoreUrls?: Array<string | RegExp>;
  captureBodies?: boolean;
}

export interface TelemetryExporterLike {
  export(payload: IngestPayload): Promise<void>;
}
