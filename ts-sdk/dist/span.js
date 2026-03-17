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
        metadata: options.metadata ?? null,
    };
    state.spans.push(span);
    return (0, context_1.withSpanContext)(span.id, async () => {
        try {
            const result = await fn();
            span.status = "success";
            return result;
        }
        catch (error) {
            span.status = "failed";
            span.metadata = {
                ...(span.metadata ?? {}),
                error: errorToMetadata(error),
            };
            throw error;
        }
        finally {
            span.ended_at = (0, run_1.isoNow)();
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
