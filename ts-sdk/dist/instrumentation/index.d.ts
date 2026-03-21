import { instrumentFetch } from "./fetch";
export declare function autoTrace(providers?: string[]): void;
export declare function autoInstrument(providers?: string[]): void;
export declare function resetAutoInstrumentation(): void;
export { instrumentFetch };
