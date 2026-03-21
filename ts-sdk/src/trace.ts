import { currentSpanId } from "./context";
import { autoTrace } from "./instrumentation";
import { addArtifact, updateSpan } from "./span";
import type { SpanRecord, TraceLogOptions } from "./types";

class TraceFacade {
  auto(providers?: string[]): void {
    autoTrace(providers);
  }

  log(message: string, options: TraceLogOptions = {}) {
    const payload: Record<string, unknown> = {
      message,
      level: options.level ?? "info",
    };

    if (options.metadata !== undefined) {
      payload.metadata = options.metadata;
    }
    if (options.timestamp !== undefined) {
      payload.timestamp = options.timestamp;
    }

    const resolvedSpanId = options.spanId === undefined ? currentSpanId() : options.spanId;
    return addArtifact("log", payload, resolvedSpanId);
  }

  updateSpan(spanId: string, data: Partial<SpanRecord>): SpanRecord {
    return updateSpan(spanId, data);
  }
}

export const trace = new TraceFacade();
