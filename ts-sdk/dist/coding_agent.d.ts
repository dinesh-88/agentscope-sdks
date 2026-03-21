import type { CommandResult, ObserveRunOptions } from "./types";
export interface RunCommandOptions {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    check?: boolean;
    shell?: boolean;
}
export declare function codingAgentRun<T>(fn: () => Promise<T> | T, options?: Omit<ObserveRunOptions, "agentName"> & {
    agentName?: string;
}): Promise<T>;
export declare function instrumentCodingAgent<TArgs extends unknown[], TResult>(fn: (...args: TArgs) => Promise<TResult> | TResult): (...args: TArgs) => Promise<TResult>;
export declare function readFile(filePath: string, encoding?: BufferEncoding): Promise<string>;
export declare function writeFile(filePath: string, content: string, encoding?: BufferEncoding): Promise<void>;
export declare function runCommand(command: string | string[], options?: RunCommandOptions): Promise<CommandResult>;
