import type { ArtifactKind, ArtifactRecord, ObserveSpanOptions, SpanRecord } from "./types";
export declare function observeSpan<T>(name: string, fn: () => Promise<T> | T, options?: ObserveSpanOptions): Promise<T>;
export declare function addArtifact(kind: ArtifactKind, payload: unknown, spanId?: string | null): ArtifactRecord;
export declare function updateSpan(spanId: string, data: Partial<SpanRecord>): SpanRecord;
