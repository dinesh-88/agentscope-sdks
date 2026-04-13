import { currentSpanId, getRunState } from "../context";
import { addArtifact, observeSpan } from "../span";
import type { FetchInstrumentationOptions } from "../types";

type FetchType = typeof globalThis.fetch;
type RequestPayload = {
  model?: unknown;
  messages?: unknown;
  input?: unknown;
  temperature?: unknown;
  tools?: unknown;
};
type ResponsePayload = {
  choices?: Array<{
    message?: {
      content?: unknown;
    };
  }>;
  usage?: {
    prompt_tokens?: unknown;
    completion_tokens?: unknown;
    input_tokens?: unknown;
    output_tokens?: unknown;
    total_tokens?: unknown;
  };
};

let originalFetch: FetchType | undefined;

export function instrumentFetch(options: FetchInstrumentationOptions = {}): () => void {
  if (typeof globalThis.fetch !== "function") {
    return () => {};
  }

  if (originalFetch) {
    return () => restoreFetch();
  }

  originalFetch = globalThis.fetch.bind(globalThis);
  const captureBodies = options.captureBodies ?? true;
  const ignoreUrls = options.ignoreUrls ?? [];
  const providerFilter = normalizeProviders(options.providers);

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const requestDetails = await readRequestDetails(input, init);
    if (shouldIgnoreUrl(requestDetails.url, ignoreUrls) || isAgentScopeIngestUrl(requestDetails.url)) {
      return originalFetch!(input, init);
    }
    if (!getRunState()) {
      return originalFetch!(input, init);
    }

    const provider = detectProvider(requestDetails.url);
    if (provider && providerFilter && !providerFilter.has(provider)) {
      return originalFetch!(input, init);
    }
    const llmRequest = provider ? detectLlmRequest(requestDetails) : null;
    const requestModel = stringifyModel(llmRequest?.model);
    const startTime = Date.now();

    return observeSpan(options.spanName ?? inferSpanName(requestDetails.url), async () => {
      if (llmRequest && captureBodies) {
        const normalizedMessages = normalizeMessages(llmRequest.messages);
        const extracted = extractSystemAndUserText(normalizedMessages, llmRequest.input);
        addArtifact("llm.prompt", {
          provider,
          model: requestModel,
          messages: normalizedMessages ?? llmRequest.messages,
          input: llmRequest.input,
          tools: llmRequest.tools,
          temperature: llmRequest.temperature,
          system_prompt: extracted.systemPrompt,
          user_input: extracted.userInput,
          payload: llmRequest,
        });
      }

      const response = await originalFetch!(input, init);
      const latencyMs = Date.now() - startTime;

      if (llmRequest) {
        const responsePayload = await safeReadJson(response.clone());
        const usage = responsePayload?.usage;
        const promptTokens = coerceNumber(usage?.prompt_tokens) ?? coerceNumber(usage?.input_tokens);
        const completionTokens = coerceNumber(usage?.completion_tokens) ?? coerceNumber(usage?.output_tokens);
        const totalTokens = coerceNumber(usage?.total_tokens) ?? (
          promptTokens !== null || completionTokens !== null
            ? (promptTokens ?? 0) + (completionTokens ?? 0)
            : null
        );

        const llmResponse = extractLlmResponse(responsePayload, {
          provider,
          model: requestModel,
          promptTokens,
          completionTokens,
          totalTokens,
        });
        if (llmResponse && captureBodies) {
          addArtifact("llm.response", llmResponse);
        }

        return finalizeResponse(response, {
          provider,
          model: requestModel,
          latencyMs,
          promptTokens,
          completionTokens,
          totalTokens,
          method: requestDetails.method,
          url: requestDetails.url,
        });
      }

      return finalizeResponse(response, {
        provider,
        model: requestModel,
        latencyMs,
        promptTokens: null,
        completionTokens: null,
        totalTokens: null,
        method: requestDetails.method,
        url: requestDetails.url,
      });
    }, {
      spanType: "http",
      provider: provider ?? undefined,
      model: requestModel ?? undefined,
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
  const baseUrl = (
    process.env.AGENTSCOPE_API_BASE
    ?? process.env.AGENTSCOPE_API
    ?? "http://localhost:8080"
  ).replace(/\/$/, "");
  return url.startsWith(`${baseUrl}/v1/ingest`);
}

function inferSpanName(url: string): string {
  if (detectProvider(url)) {
    return "llm_call";
  }
  return "fetch";
}

function detectProvider(url: string): string | null {
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase();
    const host = parsed.host.toLowerCase();

    if (hostname === "localhost" && parsed.port === "11434") {
      return "ollama";
    }
    if (hostname === "openrouter.ai" || hostname.endsWith(".openrouter.ai")) {
      return "openrouter";
    }
    if (hostname === "openai.com" || hostname.endsWith(".openai.com")) {
      return "openai";
    }
    if (hostname === "anthropic.com" || hostname.endsWith(".anthropic.com")) {
      return "anthropic";
    }
    if (hostname === "groq.com" || hostname.endsWith(".groq.com")) {
      return "groq";
    }
    if (host === "localhost:11434") {
      return "ollama";
    }
  } catch {
    return null;
  }

  return null;
}

function normalizeProviders(providers: string[] | undefined): Set<string> | null {
  if (!providers || providers.length === 0) {
    return null;
  }
  return new Set(providers.map((provider) => provider.toLowerCase()));
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

function detectLlmRequest(details: {
  url: string;
  bodyText: string | null;
}): RequestPayload | null {
  if (!detectProvider(details.url) || !details.bodyText) {
    return null;
  }

  try {
    const parsed = JSON.parse(details.bodyText) as RequestPayload;
    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }
    return {
      model: parsed.model,
      messages: parsed.messages,
      input: parsed.input,
      tools: parsed.tools,
      temperature: parsed.temperature,
    };
  } catch {
    return null;
  }
}

function messageContentToText(content: unknown): string | null {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const parts = content
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "text" in item) {
          const text = (item as { text?: unknown }).text;
          return typeof text === "string" ? text : null;
        }
        return null;
      })
      .filter((item): item is string => typeof item === "string" && item.length > 0);
    if (parts.length > 0) return parts.join("\n");
  }
  return null;
}

function normalizeMessages(raw: unknown): Array<Record<string, unknown>> | null {
  if (!Array.isArray(raw)) return null;
  return raw.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>;
}

function extractSystemAndUserText(
  messages: Array<Record<string, unknown>> | null,
  input: unknown,
): { systemPrompt?: string | null; userInput?: string | null } {
  if (messages && messages.length > 0) {
    const systemParts: string[] = [];
    const userParts: string[] = [];
    for (const message of messages) {
      const role = typeof message.role === "string" ? message.role.toLowerCase() : "";
      const content = messageContentToText(message.content);
      if (!content) continue;
      if (role === "system") systemParts.push(content);
      if (role === "user") userParts.push(content);
    }
    return {
      systemPrompt: systemParts.length > 0 ? systemParts.join("\n") : null,
      userInput: userParts.length > 0 ? userParts.join("\n") : null,
    };
  }

  if (typeof input === "string") {
    return { userInput: input, systemPrompt: null };
  }

  const inputMessages = normalizeMessages(input);
  if (inputMessages) {
    return extractSystemAndUserText(inputMessages, null);
  }

  return { systemPrompt: null, userInput: null };
}

async function safeReadJson(response: Response): Promise<ResponsePayload | null> {
  try {
    return await response.json() as ResponsePayload;
  } catch {
    return null;
  }
}

function extractLlmResponse(
  payload: ResponsePayload | null,
  details: {
    provider: string | null;
    model: string | null;
    promptTokens: number | null;
    completionTokens: number | null;
    totalTokens: number | null;
  },
): Record<string, unknown> | null {
  if (!payload) {
    return null;
  }

  return {
    provider: details.provider,
    model: details.model,
    content: payload.choices?.[0]?.message?.content ?? null,
    prompt_tokens: details.promptTokens,
    completion_tokens: details.completionTokens,
    total_tokens: details.totalTokens,
    usage: {
      input_tokens: details.promptTokens,
      output_tokens: details.completionTokens,
      total_tokens: details.totalTokens,
    },
    response: payload,
  };
}

function finalizeResponse(
  response: Response,
  details: {
    provider: string | null;
    model: string | null;
    latencyMs: number;
    promptTokens: number | null;
    completionTokens: number | null;
    totalTokens: number | null;
    method: string;
    url: string;
  },
): Response {
  const state = getRunState();
  const spanId = currentSpanId();
  const currentSpan = state?.spans.find((span) => span.id === spanId);
  if (!currentSpan) {
    return response;
  }

  currentSpan.provider = details.provider;
  currentSpan.model = details.model;
  currentSpan.input_tokens = details.promptTokens;
  currentSpan.output_tokens = details.completionTokens;
  currentSpan.total_tokens = details.totalTokens;
  currentSpan.metadata = {
    ...(currentSpan.metadata ?? {}),
    method: details.method,
    url: details.url,
    provider: details.provider,
    model: details.model,
    latency_ms: details.latencyMs,
    input_tokens: details.promptTokens,
    output_tokens: details.completionTokens,
    total_tokens: details.totalTokens,
  };

  return response;
}

function coerceNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringifyModel(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
