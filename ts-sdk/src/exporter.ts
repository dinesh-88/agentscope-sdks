import { AgentScopeClient } from "./client";
import type { IngestPayload, TelemetryExporterLike } from "./types";

const pendingExports = new Set<Promise<void>>();

export class TelemetryExporter implements TelemetryExporterLike {
  constructor(private readonly client: AgentScopeClient = new AgentScopeClient()) {}

  export(payload: IngestPayload): Promise<void> {
    const task = this.client.ingest(payload).finally(() => {
      pendingExports.delete(task);
    });
    pendingExports.add(task);
    return task;
  }
}

export async function flushPendingExports(): Promise<void> {
  while (pendingExports.size > 0) {
    await Promise.all([...pendingExports]);
  }
}
