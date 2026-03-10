import { AsyncLocalStorage } from "node:async_hooks";

import type { ArtifactRecord, RunRecord, SpanRecord, TelemetryExporterLike } from "./types";

export interface RunState {
  run: RunRecord;
  spans: SpanRecord[];
  artifacts: ArtifactRecord[];
  exporter: TelemetryExporterLike;
  spanStack: string[];
}

const contextStorage = new AsyncLocalStorage<RunState>();

export function getRunState(): RunState | undefined {
  return contextStorage.getStore();
}

export function withRunState<T>(state: RunState, fn: () => Promise<T>): Promise<T> {
  return contextStorage.run(state, fn);
}

export function currentSpanId(): string | null {
  const state = getRunState();
  if (!state || state.spanStack.length === 0) {
    return null;
  }
  return state.spanStack[state.spanStack.length - 1] ?? null;
}

export async function withSpanContext<T>(spanId: string, fn: () => Promise<T>): Promise<T> {
  const state = getRunState();
  if (!state) {
    throw new Error("observeSpan must be called inside observeRun");
  }

  const nextState: RunState = {
    ...state,
    spanStack: [...state.spanStack, spanId],
  };

  return contextStorage.run(nextState, fn);
}
