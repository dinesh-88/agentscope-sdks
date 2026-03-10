import type { AgentScopeClientOptions, IngestPayload } from "./types";
export declare class AgentScopeClient {
    private readonly baseUrl;
    private readonly apiKey;
    private readonly timeoutMs;
    constructor(options?: AgentScopeClientOptions);
    ingest(payload: IngestPayload): Promise<void>;
}
