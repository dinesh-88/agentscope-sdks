import { randomUUID } from "node:crypto";

import { withRunState, type RunState } from "./context";
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
    workflow_name: workflowName,
    agent_name: options.agentName ?? workflowName,
    status: "running",
    started_at: isoNow(),
    ended_at: null,
  };

  const state: RunState = {
    run,
    spans: [],
    artifacts: [],
    exporter: options.exporter ?? new TelemetryExporter(),
    spanStack: [],
  };

  return withRunState(state, async () => {
    let callbackError: unknown;

    try {
      const result = await fn();
      run.status = "success";
      return result;
    } catch (error) {
      run.status = "failed";
      callbackError = error;
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
