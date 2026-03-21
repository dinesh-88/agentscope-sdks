export type ArtifactKind = "llm.prompt" | "llm.response" | "tool.input" | "tool.output" | "file.diff" | "file.content" | "log" | "error" | "command.stdout" | "command.stderr";
export interface RunRecord {
    id: string;
    project_id: string;
    organization_id?: string | null;
    user_id?: string | null;
    session_id?: string | null;
    environment?: "prod" | "staging" | "dev" | null;
    workflow_name: string;
    agent_name: string;
    status: "running" | "success" | "failed";
    started_at: string;
    ended_at: string | null;
    total_input_tokens?: number;
    total_output_tokens?: number;
    total_tokens?: number;
    total_cost_usd?: number;
    success?: boolean | null;
    error_count?: number | null;
    avg_latency_ms?: number | null;
    p95_latency_ms?: number | null;
    success_rate?: number | null;
    tags?: string[] | null;
    experiment_id?: string | null;
    variant?: string | null;
    metadata?: Record<string, unknown> | null;
}
export interface SpanErrorRecord {
    error_type?: "invalid_json" | "rate_limit" | "timeout" | "tool_error" | "unknown";
    error_source?: "provider" | "tool" | "system";
    retryable?: boolean;
    metadata?: Record<string, unknown> | null;
}
export interface SpanEvaluationRecord {
    success?: boolean;
    score?: number;
    reason?: string;
    evaluator?: "rule" | "llm" | "user";
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
    latency_ms?: number | null;
    success?: boolean | null;
    error_type?: "invalid_json" | "rate_limit" | "timeout" | "tool_error" | "unknown" | null;
    error_source?: "provider" | "tool" | "system" | null;
    retryable?: boolean | null;
    prompt_hash?: string | null;
    prompt_template_id?: string | null;
    temperature?: number | null;
    top_p?: number | null;
    max_tokens?: number | null;
    retry_attempt?: number | null;
    max_attempts?: number | null;
    tool_name?: string | null;
    tool_version?: string | null;
    tool_latency_ms?: number | null;
    tool_success?: boolean | null;
    evaluation?: SpanEvaluationRecord | null;
    metadata?: Record<string, unknown> | null;
    error?: SpanErrorRecord | null;
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
    userId?: string;
    sessionId?: string;
    environment?: "prod" | "staging" | "dev";
    tags?: string[];
    experimentId?: string;
    variant?: string;
    metadata?: Record<string, unknown>;
    exporter?: TelemetryExporterLike;
    liveStream?: boolean;
}
export interface ObserveSpanOptions {
    spanType?: string;
    metadata?: Record<string, unknown>;
    error?: SpanErrorRecord;
    evaluation?: SpanEvaluationRecord;
    prompt?: string;
    promptTemplateId?: string;
    provider?: string;
    model?: string;
    inputTokens?: number;
    outputTokens?: number;
    totalTokens?: number;
    estimatedCost?: number;
    contextWindow?: number;
    contextUsagePercent?: number;
    temperature?: number;
    topP?: number;
    maxTokens?: number;
    retryAttempt?: number;
    maxAttempts?: number;
    toolName?: string;
    toolVersion?: string;
    toolLatencyMs?: number;
    toolSuccess?: boolean;
    responseText?: string;
}
export interface FetchInstrumentationOptions {
    spanName?: string;
    ignoreUrls?: Array<string | RegExp>;
    captureBodies?: boolean;
    providers?: string[];
}
export interface TraceLogOptions {
    level?: string;
    spanId?: string | null;
    metadata?: Record<string, unknown>;
    timestamp?: string;
}
export interface CommandResult {
    command: string;
    exitCode: number;
    stdout: string;
    stderr: string;
}
export interface TelemetryExporterLike {
    export(payload: IngestPayload): Promise<void>;
}
