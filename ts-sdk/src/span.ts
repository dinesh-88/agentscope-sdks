import { createHash, randomUUID } from "node:crypto";

import { currentSpanId, getRunState, withSpanContext } from "./context";
import { isoNow } from "./run";
import type { ArtifactKind, ArtifactRecord, ObserveSpanOptions, SpanRecord } from "./types";

export async function observeSpan<T>(
  name: string,
  fn: () => Promise<T> | T,
  options: ObserveSpanOptions = {},
): Promise<T> {
  const state = getRunState();
  if (!state) {
    throw new Error("observeSpan must be called inside observeRun");
  }

  const span: SpanRecord = {
    id: randomUUID(),
    run_id: state.run.id,
    parent_span_id: currentSpanId(),
    span_type: options.spanType ?? name,
    name,
    status: "running",
    started_at: isoNow(),
    ended_at: null,
    provider: options.provider ?? null,
    model: options.model ?? null,
    input_tokens: options.inputTokens ?? null,
    output_tokens: options.outputTokens ?? null,
    total_tokens: options.totalTokens ?? null,
    estimated_cost: options.estimatedCost ?? null,
    context_window: options.contextWindow ?? null,
    context_usage_percent: options.contextUsagePercent ?? null,
    latency_ms: null,
    success: null,
    error_type: options.error?.error_type ?? null,
    error_source: options.error?.error_source ?? null,
    retryable: options.error?.retryable ?? null,
    prompt_hash: options.prompt ? promptHash(options.prompt) : null,
    prompt_template_id: options.promptTemplateId ?? null,
    temperature: options.temperature ?? null,
    top_p: options.topP ?? null,
    max_tokens: options.maxTokens ?? null,
    retry_attempt: options.retryAttempt ?? null,
    max_attempts: options.maxAttempts ?? null,
    tool_name: options.toolName ?? null,
    tool_version: options.toolVersion ?? null,
    tool_latency_ms: options.toolLatencyMs ?? null,
    tool_success: options.toolSuccess ?? null,
    evaluation: options.evaluation ?? evaluateResponse(options.responseText),
    metadata: options.metadata ?? null,
    error: options.error ?? null,
  };

  state.spans.push(span);

  return withSpanContext(span.id, async () => {
    try {
      const result = await fn();
      span.status = "success";
      span.success = true;
      return result;
    } catch (error) {
      span.status = "failed";
      span.success = false;
      span.error_type = span.error_type ?? "unknown";
      span.error_source = span.error_source ?? "system";
      span.metadata = {
        ...(span.metadata ?? {}),
        error: errorToMetadata(error),
      };
      throw error;
    } finally {
      span.ended_at = isoNow();
      span.latency_ms = elapsedMs(span.started_at, span.ended_at);
    }
  });
}

export function addArtifact(kind: ArtifactKind, payload: unknown): ArtifactRecord {
  const state = getRunState();
  if (!state) {
    throw new Error("addArtifact must be called inside observeRun");
  }

  const artifact: ArtifactRecord = {
    id: randomUUID(),
    run_id: state.run.id,
    span_id: currentSpanId(),
    kind,
    payload,
  };

  state.artifacts.push(artifact);
  return artifact;
}

function errorToMetadata(error: unknown): Record<string, unknown> {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack,
    };
  }

  return {
    value: String(error),
  };
}

function promptHash(prompt: string): string {
  const normalized = prompt.replace(/\r\n/g, "\n").trim().replace(/[ \t]+/g, " ");
  return createHash("sha256").update(normalized).digest("hex");
}

function evaluateResponse(responseText: string | undefined): SpanRecord["evaluation"] {
  if (responseText === undefined) return null;
  const trimmed = responseText.trim();
  if (!trimmed) {
    return {
      success: false,
      score: 0,
      reason: "Empty response",
      evaluator: "rule",
    };
  }

  try {
    JSON.parse(trimmed);
    return {
      success: true,
      score: 1,
      reason: "Valid JSON response",
      evaluator: "rule",
    };
  } catch {
    return {
      success: false,
      score: 0,
      reason: "Invalid JSON response",
      evaluator: "rule",
    };
  }
}

function elapsedMs(startedAt: string, endedAt: string): number {
  const ms = Date.parse(endedAt) - Date.parse(startedAt);
  return Number.isFinite(ms) && ms > 0 ? ms : 0;
}
