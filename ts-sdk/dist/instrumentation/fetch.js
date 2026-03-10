"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.instrumentFetch = instrumentFetch;
const context_1 = require("../context");
const span_1 = require("../span");
let originalFetch;
function instrumentFetch(options = {}) {
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
        const openAiRequest = captureBodies ? detectOpenAiRequest(requestDetails) : null;
        return (0, span_1.observeSpan)(options.spanName ?? inferSpanName(requestDetails.url), async () => {
            if (openAiRequest) {
                (0, span_1.addArtifact)("llm.prompt", openAiRequest);
            }
            const response = await originalFetch(input, init);
            if (openAiRequest && captureBodies) {
                const responsePayload = await safeReadJson(response.clone());
                if (responsePayload) {
                    (0, span_1.addArtifact)("llm.response", responsePayload);
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
    if (isOpenAiCompatibleUrl(url)) {
        return "llm_call";
    }
    return "fetch";
}
function isOpenAiCompatibleUrl(url) {
    return /\/v1\/(chat\/completions|responses)$/.test(url) || /\/chat\/completions$/.test(url);
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
function detectOpenAiRequest(details) {
    if (!isOpenAiCompatibleUrl(details.url) || !details.bodyText) {
        return null;
    }
    try {
        const parsed = JSON.parse(details.bodyText);
        if (!("model" in parsed) || !("messages" in parsed)) {
            return null;
        }
        return {
            model: parsed.model,
            messages: parsed.messages,
            tools: parsed.tools,
            stream: parsed.stream,
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
