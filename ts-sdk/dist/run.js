"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.observeRun = observeRun;
exports.isoNow = isoNow;
exports.scheduleLiveFlush = scheduleLiveFlush;
const node_crypto_1 = require("node:crypto");
const context_1 = require("./context");
const exporter_1 = require("./exporter");
const DEFAULT_PROJECT_ID = "00000000-0000-4000-8000-000000000001";
async function observeRun(workflowName, fn, options = {}) {
    const run = {
        id: (0, node_crypto_1.randomUUID)(),
        project_id: options.projectId ?? DEFAULT_PROJECT_ID,
        organization_id: null,
        user_id: options.userId ?? null,
        session_id: options.sessionId ?? null,
        environment: options.environment ?? null,
        workflow_name: workflowName,
        agent_name: options.agentName ?? workflowName,
        status: "running",
        started_at: isoNow(),
        ended_at: null,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_tokens: 0,
        total_cost_usd: 0,
        success: null,
        error_count: 0,
        avg_latency_ms: null,
        p95_latency_ms: null,
        success_rate: null,
        tags: options.tags ?? null,
        experiment_id: options.experimentId ?? null,
        variant: options.variant ?? null,
        metadata: options.metadata ?? null,
    };
    const state = {
        run,
        spans: [],
        artifacts: [],
        exporter: options.exporter ?? new exporter_1.TelemetryExporter(),
        spanStack: [],
        liveStreamEnabled: options.liveStream ?? envLiveStreamDefault(),
    };
    return (0, context_1.withRunState)(state, async () => {
        let callbackError;
        scheduleLiveFlush(state);
        try {
            const result = await fn();
            run.status = "success";
            run.success = true;
            return result;
        }
        catch (error) {
            run.status = "failed";
            run.success = false;
            callbackError = error;
            state.artifacts.push({
                id: (0, node_crypto_1.randomUUID)(),
                run_id: run.id,
                span_id: null,
                kind: "error",
                payload: errorPayload(error),
            });
            throw error;
        }
        finally {
            run.ended_at = isoNow();
            try {
                await state.exporter.export({
                    run,
                    spans: state.spans,
                    artifacts: state.artifacts,
                });
                await (0, exporter_1.flushPendingExports)();
            }
            catch (exportError) {
                if (callbackError) {
                    console.warn("AgentScope export failed after run error:", exportError);
                }
                else {
                    console.warn("AgentScope export failed:", exportError);
                }
            }
        }
    });
}
function isoNow() {
    return new Date().toISOString();
}
function scheduleLiveFlush(state = (0, context_1.getRunState)()) {
    if (!state || !state.liveStreamEnabled) {
        return;
    }
    void state
        .exporter
        .export({
        run: state.run,
        spans: state.spans,
        artifacts: state.artifacts,
    })
        .catch((error) => {
        console.warn("AgentScope live export failed:", error);
    });
}
function envLiveStreamDefault() {
    const raw = (process.env.AGENTSCOPE_LIVE_STREAM ?? "true").trim().toLowerCase();
    return !["0", "false", "off", "no"].includes(raw);
}
function errorPayload(error) {
    if (error instanceof Error) {
        return {
            error_type: error.name || "Error",
            message: error.message,
        };
    }
    return {
        error_type: "Error",
        message: String(error),
    };
}
