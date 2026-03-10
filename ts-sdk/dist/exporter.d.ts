import { AgentScopeClient } from "./client";
import type { IngestPayload, TelemetryExporterLike } from "./types";
export declare class TelemetryExporter implements TelemetryExporterLike {
    private readonly client;
    constructor(client?: AgentScopeClient);
    export(payload: IngestPayload): Promise<void>;
}
export declare function flushPendingExports(): Promise<void>;
