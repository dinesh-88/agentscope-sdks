"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.observeRun = observeRun;
exports.isoNow = isoNow;
const node_crypto_1 = require("node:crypto");
const context_1 = require("./context");
const exporter_1 = require("./exporter");
const DEFAULT_PROJECT_ID = "00000000-0000-4000-8000-000000000001";
async function observeRun(workflowName, fn, options = {}) {
    const run = {
        id: (0, node_crypto_1.randomUUID)(),
        project_id: options.projectId ?? DEFAULT_PROJECT_ID,
        workflow_name: workflowName,
        agent_name: options.agentName ?? workflowName,
        status: "running",
        started_at: isoNow(),
        ended_at: null,
    };
    const state = {
        run,
        spans: [],
        artifacts: [],
        exporter: options.exporter ?? new exporter_1.TelemetryExporter(),
        spanStack: [],
    };
    return (0, context_1.withRunState)(state, async () => {
        let callbackError;
        try {
            const result = await fn();
            run.status = "success";
            return result;
        }
        catch (error) {
            run.status = "failed";
            callbackError = error;
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
