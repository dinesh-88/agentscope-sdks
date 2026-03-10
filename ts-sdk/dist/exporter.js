"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.TelemetryExporter = void 0;
exports.flushPendingExports = flushPendingExports;
const client_1 = require("./client");
const pendingExports = new Set();
class TelemetryExporter {
    client;
    constructor(client = new client_1.AgentScopeClient()) {
        this.client = client;
    }
    export(payload) {
        const task = this.client.ingest(payload).finally(() => {
            pendingExports.delete(task);
        });
        pendingExports.add(task);
        return task;
    }
}
exports.TelemetryExporter = TelemetryExporter;
async function flushPendingExports() {
    while (pendingExports.size > 0) {
        await Promise.all([...pendingExports]);
    }
}
