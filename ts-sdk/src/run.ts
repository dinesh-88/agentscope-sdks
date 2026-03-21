import { randomUUID } from "node:crypto";

import { getRunState, withRunState, type RunState } from "./context";
import { TelemetryExporter, flushPendingExports } from "./exporter";
import type { ObserveRunOptions, RunRecord } from "./types";

const DEFAULT_PROJECT_ID = "00000000-0000-4000-8000-000000000001";

export async function observeRun<T>(
  workflowName: string,
  fn: () => Promise<T> | T,
  options: ObserveRunOptions = {},
): Promise<T> {
  const run: RunRecord = {
    id: randomUUID(),
    project_id: options.projectId ?? DEFAULT_PROJECT_ID,
    organization_id: null,
    user_id: options.userId ?? null,
    session_id: options.sessionId ?? null,
    environment: options.environment ?? null,
    workflow_name: workflowName,
    agent_name: options.agentName ?? workflowName,
    status: "running",
    started_at: isoNow(),
    ended_at: null,
    total_input_tokens: 0,
    total_output_tokens: 0,
    total_tokens: 0,
    total_cost_usd: 0,
    success: null,
    error_count: 0,
    avg_latency_ms: null,
    p95_latency_ms: null,
    success_rate: null,
    tags: options.tags ?? null,
    experiment_id: options.experimentId ?? null,
    variant: options.variant ?? null,
    metadata: options.metadata ?? null,
  };

  const state: RunState = {
    run,
    spans: [],
    artifacts: [],
    exporter: options.exporter ?? new TelemetryExporter(),
    spanStack: [],
    liveStreamEnabled: options.liveStream ?? envLiveStreamDefault(),
  };

  return withRunState(state, async () => {
    let callbackError: unknown;
    scheduleLiveFlush(state);

    try {
      const result = await fn();
      run.status = "success";
      run.success = true;
      return result;
    } catch (error) {
      run.status = "failed";
      run.success = false;
      callbackError = error;
      state.artifacts.push({
        id: randomUUID(),
        run_id: run.id,
        span_id: null,
        kind: "error",
        payload: errorPayload(error),
      });
      throw error;
    } finally {
      run.ended_at = isoNow();
      try {
        await state.exporter.export({
          run,
          spans: state.spans,
          artifacts: state.artifacts,
        });
        await flushPendingExports();
      } catch (exportError) {
        if (callbackError) {
          console.warn("AgentScope export failed after run error:", exportError);
        } else {
          console.warn("AgentScope export failed:", exportError);
        }
      }
    }
  });
}

export function isoNow(): string {
  return new Date().toISOString();
}

export function scheduleLiveFlush(state: RunState | undefined = getRunState()): void {
  if (!state || !state.liveStreamEnabled) {
    return;
  }

  void state
    .exporter
    .export({
      run: state.run,
      spans: state.spans,
      artifacts: state.artifacts,
    })
    .catch((error) => {
      console.warn("AgentScope live export failed:", error);
    });
}

function envLiveStreamDefault(): boolean {
  const raw = (process.env.AGENTSCOPE_LIVE_STREAM ?? "true").trim().toLowerCase();
  return !["0", "false", "off", "no"].includes(raw);
}

function errorPayload(error: unknown): Record<string, string> {
  if (error instanceof Error) {
    return {
      error_type: error.name || "Error",
      message: error.message,
    };
  }
  return {
    error_type: "Error",
    message: String(error),
  };
}
