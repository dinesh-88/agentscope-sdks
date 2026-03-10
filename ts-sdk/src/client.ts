import type { AgentScopeClientOptions, IngestPayload } from "./types";

export class AgentScopeClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: AgentScopeClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? process.env.AGENTSCOPE_API ?? "http://localhost:8080").replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? 5000;
  }

  async ingest(payload: IngestPayload): Promise<void> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}/v1/ingest`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`AgentScope ingest failed with status ${response.status}`);
      }
    } finally {
      clearTimeout(timeout);
    }
  }
}
