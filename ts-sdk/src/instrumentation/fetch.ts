import { getRunState } from "../context";
import { addArtifact, observeSpan } from "../span";
import type { FetchInstrumentationOptions } from "../types";

type FetchType = typeof globalThis.fetch;

let originalFetch: FetchType | undefined;

export function instrumentFetch(options: FetchInstrumentationOptions = {}): () => void {
  if (originalFetch) {
    return () => restoreFetch();
  }

  originalFetch = globalThis.fetch.bind(globalThis);
  const captureBodies = options.captureBodies ?? true;
  const ignoreUrls = options.ignoreUrls ?? [];

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const requestDetails = await readRequestDetails(input, init);
    if (shouldIgnoreUrl(requestDetails.url, ignoreUrls) || isAgentScopeIngestUrl(requestDetails.url)) {
      return originalFetch!(input, init);
    }
    if (!getRunState()) {
      return originalFetch!(input, init);
    }

    const openAiRequest = captureBodies ? detectOpenAiRequest(requestDetails) : null;

    return observeSpan(options.spanName ?? inferSpanName(requestDetails.url), async () => {
      if (openAiRequest) {
        addArtifact("llm.prompt", openAiRequest);
      }

      const response = await originalFetch!(input, init);

      if (openAiRequest && captureBodies) {
        const responsePayload = await safeReadJson(response.clone());
        if (responsePayload) {
          addArtifact("llm.response", responsePayload);
        }
      }

      return response;
    }, {
      spanType: "http",
      metadata: {
        method: requestDetails.method,
        url: requestDetails.url,
      },
    });
  };

  return () => restoreFetch();
}

function restoreFetch(): void {
  if (!originalFetch) {
    return;
  }

  globalThis.fetch = originalFetch;
  originalFetch = undefined;
}

function shouldIgnoreUrl(url: string, patterns: Array<string | RegExp>): boolean {
  return patterns.some((pattern) => {
    if (typeof pattern === "string") {
      return url.includes(pattern);
    }
    return pattern.test(url);
  });
}

function isAgentScopeIngestUrl(url: string): boolean {
  const baseUrl = (process.env.AGENTSCOPE_API ?? "http://localhost:8080").replace(/\/$/, "");
  return url.startsWith(`${baseUrl}/v1/ingest`);
}

function inferSpanName(url: string): string {
  if (isOpenAiCompatibleUrl(url)) {
    return "llm_call";
  }
  return "fetch";
}

function isOpenAiCompatibleUrl(url: string): boolean {
  return /\/v1\/(chat\/completions|responses)$/.test(url) || /\/chat\/completions$/.test(url);
}

async function readRequestDetails(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<{ url: string; method: string; bodyText: string | null }> {
  if (input instanceof Request) {
    const clone = input.clone();
    return {
      url: clone.url,
      method: init?.method ?? clone.method ?? "GET",
      bodyText: await safeReadText(clone),
    };
  }

  return {
    url: String(input),
    method: init?.method ?? "GET",
    bodyText: bodyToText(init?.body),
  };
}

function bodyToText(body: RequestInit["body"] | null | undefined): string | null {
  if (typeof body === "string") {
    return body;
  }
  if (body instanceof URLSearchParams) {
    return body.toString();
  }
  return null;
}

async function safeReadText(request: Request): Promise<string | null> {
  try {
    const text = await request.text();
    return text.length > 0 ? text : null;
  } catch {
    return null;
  }
}

function detectOpenAiRequest(details: {
  url: string;
  bodyText: string | null;
}): Record<string, unknown> | null {
  if (!isOpenAiCompatibleUrl(details.url) || !details.bodyText) {
    return null;
  }

  try {
    const parsed = JSON.parse(details.bodyText) as Record<string, unknown>;
    if (!("model" in parsed) || !("messages" in parsed)) {
      return null;
    }
    return {
      model: parsed.model,
      messages: parsed.messages,
      tools: parsed.tools,
      stream: parsed.stream,
    };
  } catch {
    return null;
  }
}

async function safeReadJson(response: Response): Promise<unknown | null> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}
