import type { SpanRecord, TraceLogOptions } from "./types";
declare class TraceFacade {
    auto(providers?: string[]): void;
    log(message: string, options?: TraceLogOptions): import("./types").ArtifactRecord;
    updateSpan(spanId: string, data: Partial<SpanRecord>): SpanRecord;
}
export declare const trace: TraceFacade;
export {};
