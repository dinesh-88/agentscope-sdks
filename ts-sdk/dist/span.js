"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.observeSpan = observeSpan;
exports.addArtifact = addArtifact;
const node_crypto_1 = require("node:crypto");
const context_1 = require("./context");
const run_1 = require("./run");
async function observeSpan(name, fn, options = {}) {
    const state = (0, context_1.getRunState)();
    if (!state) {
        throw new Error("observeSpan must be called inside observeRun");
    }
    const span = {
        id: (0, node_crypto_1.randomUUID)(),
        run_id: state.run.id,
        parent_span_id: (0, context_1.currentSpanId)(),
        span_type: options.spanType ?? name,
        name,
        status: "running",
        started_at: (0, run_1.isoNow)(),
        ended_at: null,
        provider: options.provider ?? null,
        model: options.model ?? null,
        input_tokens: options.inputTokens ?? null,
        output_tokens: options.outputTokens ?? null,
        total_tokens: options.totalTokens ?? null,
        estimated_cost: options.estimatedCost ?? null,
        context_window: options.contextWindow ?? null,
        context_usage_percent: options.contextUsagePercent ?? null,
        latency_ms: null,
        success: null,
        error_type: options.error?.error_type ?? null,
        error_source: options.error?.error_source ?? null,
        retryable: options.error?.retryable ?? null,
        prompt_hash: options.prompt ? promptHash(options.prompt) : null,
        prompt_template_id: options.promptTemplateId ?? null,
        temperature: options.temperature ?? null,
        top_p: options.topP ?? null,
        max_tokens: options.maxTokens ?? null,
        retry_attempt: options.retryAttempt ?? null,
        max_attempts: options.maxAttempts ?? null,
        tool_name: options.toolName ?? null,
        tool_version: options.toolVersion ?? null,
        tool_latency_ms: options.toolLatencyMs ?? null,
        tool_success: options.toolSuccess ?? null,
        evaluation: options.evaluation ?? evaluateResponse(options.responseText),
        metadata: options.metadata ?? null,
        error: options.error ?? null,
    };
    state.spans.push(span);
    return (0, context_1.withSpanContext)(span.id, async () => {
        try {
            const result = await fn();
            span.status = "success";
            span.success = true;
            return result;
        }
        catch (error) {
            span.status = "failed";
            span.success = false;
            span.error_type = span.error_type ?? "unknown";
            span.error_source = span.error_source ?? "system";
            span.metadata = {
                ...(span.metadata ?? {}),
                error: errorToMetadata(error),
            };
            throw error;
        }
        finally {
            span.ended_at = (0, run_1.isoNow)();
            span.latency_ms = elapsedMs(span.started_at, span.ended_at);
        }
    });
}
function addArtifact(kind, payload) {
    const state = (0, context_1.getRunState)();
    if (!state) {
        throw new Error("addArtifact must be called inside observeRun");
    }
    const artifact = {
        id: (0, node_crypto_1.randomUUID)(),
        run_id: state.run.id,
        span_id: (0, context_1.currentSpanId)(),
        kind,
        payload,
    };
    state.artifacts.push(artifact);
    return artifact;
}
function errorToMetadata(error) {
    if (error instanceof Error) {
        return {
            name: error.name,
            message: error.message,
            stack: error.stack,
        };
    }
    return {
        value: String(error),
    };
}
function promptHash(prompt) {
    const normalized = prompt.replace(/\r\n/g, "\n").trim().replace(/[ \t]+/g, " ");
    return (0, node_crypto_1.createHash)("sha256").update(normalized).digest("hex");
}
function evaluateResponse(responseText) {
    if (responseText === undefined)
        return null;
    const trimmed = responseText.trim();
    if (!trimmed) {
        return {
            success: false,
            score: 0,
            reason: "Empty response",
            evaluator: "rule",
        };
    }
    try {
        JSON.parse(trimmed);
        return {
            success: true,
            score: 1,
            reason: "Valid JSON response",
            evaluator: "rule",
        };
    }
    catch {
        return {
            success: false,
            score: 0,
            reason: "Invalid JSON response",
            evaluator: "rule",
        };
    }
}
function elapsedMs(startedAt, endedAt) {
    const ms = Date.parse(endedAt) - Date.parse(startedAt);
    return Number.isFinite(ms) && ms > 0 ? ms : 0;
}
