import { instrumentFetch } from "./instrumentation";

export { AgentScopeClient } from "./client";
export { observeRun } from "./run";
export { addArtifact, observeSpan } from "./span";
export { TelemetryExporter, flushPendingExports as flush } from "./exporter";
export * from "./types";
export * from "./instrumentation";

instrumentFetch();
