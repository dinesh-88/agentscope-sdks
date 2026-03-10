import type { ArtifactRecord, RunRecord, SpanRecord, TelemetryExporterLike } from "./types";
export interface RunState {
    run: RunRecord;
    spans: SpanRecord[];
    artifacts: ArtifactRecord[];
    exporter: TelemetryExporterLike;
    spanStack: string[];
}
export declare function getRunState(): RunState | undefined;
export declare function withRunState<T>(state: RunState, fn: () => Promise<T>): Promise<T>;
export declare function currentSpanId(): string | null;
export declare function withSpanContext<T>(spanId: string, fn: () => Promise<T>): Promise<T>;
