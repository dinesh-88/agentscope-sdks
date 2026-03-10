import { randomUUID } from "node:crypto";

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
    metadata: options.metadata ?? null,
  };

  state.spans.push(span);

  return withSpanContext(span.id, async () => {
    try {
      const result = await fn();
      span.status = "success";
      return result;
    } catch (error) {
      span.status = "failed";
      span.metadata = {
        ...(span.metadata ?? {}),
        error: errorToMetadata(error),
      };
      throw error;
    } finally {
      span.ended_at = isoNow();
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
