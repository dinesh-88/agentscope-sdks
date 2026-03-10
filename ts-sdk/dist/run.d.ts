import type { ObserveRunOptions } from "./types";
export declare function observeRun<T>(workflowName: string, fn: () => Promise<T> | T, options?: ObserveRunOptions): Promise<T>;
export declare function isoNow(): string;
