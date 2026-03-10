"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.instrumentFetch = instrumentFetch;
const context_1 = require("../context");
const span_1 = require("../span");
let originalFetch;
function instrumentFetch(options = {}) {
    if (typeof globalThis.fetch !== "function") {
        return () => { };
    }
    if (originalFetch) {
        return () => restoreFetch();
    }
    originalFetch = globalThis.fetch.bind(globalThis);
    const captureBodies = options.captureBodies ?? true;
    const ignoreUrls = options.ignoreUrls ?? [];
    globalThis.fetch = async (input, init) => {
        const requestDetails = await readRequestDetails(input, init);
        if (shouldIgnoreUrl(requestDetails.url, ignoreUrls) || isAgentScopeIngestUrl(requestDetails.url)) {
            return originalFetch(input, init);
        }
        if (!(0, context_1.getRunState)()) {
            return originalFetch(input, init);
        }
        const provider = detectProvider(requestDetails.url);
        const llmRequest = provider ? detectLlmRequest(requestDetails) : null;
        const requestModel = stringifyModel(llmRequest?.model);
        const startTime = Date.now();
        return (0, span_1.observeSpan)(options.spanName ?? inferSpanName(requestDetails.url), async () => {
            if (llmRequest && captureBodies) {
                (0, span_1.addArtifact)("llm.prompt", llmRequest);
            }
            const response = await originalFetch(input, init);
            const latencyMs = Date.now() - startTime;
            if (llmRequest) {
                const responsePayload = await safeReadJson(response.clone());
                const llmResponse = extractLlmResponse(responsePayload);
                if (llmResponse && captureBodies) {
                    (0, span_1.addArtifact)("llm.response", llmResponse);
                }
                const usage = responsePayload?.usage;
                const promptTokens = coerceNumber(usage?.prompt_tokens);
                const completionTokens = coerceNumber(usage?.completion_tokens);
                return finalizeResponse(response, {
                    provider,
                    model: requestModel,
                    latencyMs,
                    promptTokens,
                    completionTokens,
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
function restoreFetch() {
    if (!originalFetch) {
        return;
    }
    globalThis.fetch = originalFetch;
    originalFetch = undefined;
}
function shouldIgnoreUrl(url, patterns) {
    return patterns.some((pattern) => {
        if (typeof pattern === "string") {
            return url.includes(pattern);
        }
        return pattern.test(url);
    });
}
function isAgentScopeIngestUrl(url) {
    const baseUrl = (process.env.AGENTSCOPE_API ?? "http://localhost:8080").replace(/\/$/, "");
    return url.startsWith(`${baseUrl}/v1/ingest`);
}
function inferSpanName(url) {
    if (detectProvider(url)) {
        return "llm_call";
    }
    return "fetch";
}
function detectProvider(url) {
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
    }
    catch {
        return null;
    }
    return null;
}
async function readRequestDetails(input, init) {
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
function bodyToText(body) {
    if (typeof body === "string") {
        return body;
    }
    if (body instanceof URLSearchParams) {
        return body.toString();
    }
    return null;
}
async function safeReadText(request) {
    try {
        const text = await request.text();
        return text.length > 0 ? text : null;
    }
    catch {
        return null;
    }
}
function detectLlmRequest(details) {
    if (!detectProvider(details.url) || !details.bodyText) {
        return null;
    }
    try {
        const parsed = JSON.parse(details.bodyText);
        if (typeof parsed !== "object" || parsed === null) {
            return null;
        }
        return {
            model: parsed.model,
            messages: parsed.messages,
            tools: parsed.tools,
            temperature: parsed.temperature,
        };
    }
    catch {
        return null;
    }
}
async function safeReadJson(response) {
    try {
        return await response.json();
    }
    catch {
        return null;
    }
}
function extractLlmResponse(payload) {
    if (!payload) {
        return null;
    }
    return {
        content: payload.choices?.[0]?.message?.content ?? null,
        prompt_tokens: payload.usage?.prompt_tokens ?? null,
        completion_tokens: payload.usage?.completion_tokens ?? null,
    };
}
function finalizeResponse(response, details) {
    const state = (0, context_1.getRunState)();
    const spanId = (0, context_1.currentSpanId)();
    const currentSpan = state?.spans.find((span) => span.id === spanId);
    if (!currentSpan) {
        return response;
    }
    currentSpan.provider = details.provider;
    currentSpan.model = details.model;
    currentSpan.input_tokens = details.promptTokens;
    currentSpan.output_tokens = details.completionTokens;
    currentSpan.metadata = {
        ...(currentSpan.metadata ?? {}),
        method: details.method,
        url: details.url,
        provider: details.provider,
        model: details.model,
        latency_ms: details.latencyMs,
        input_tokens: details.promptTokens,
        output_tokens: details.completionTokens,
    };
    return response;
}
function coerceNumber(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function stringifyModel(value) {
    return typeof value === "string" && value.length > 0 ? value : null;
}
