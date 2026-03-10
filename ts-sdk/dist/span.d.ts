import type { ArtifactKind, ArtifactRecord, ObserveSpanOptions } from "./types";
export declare function observeSpan<T>(name: string, fn: () => Promise<T> | T, options?: ObserveSpanOptions): Promise<T>;
export declare function addArtifact(kind: ArtifactKind, payload: unknown): ArtifactRecord;
