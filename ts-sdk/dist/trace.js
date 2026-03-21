"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.trace = void 0;
const context_1 = require("./context");
const instrumentation_1 = require("./instrumentation");
const span_1 = require("./span");
class TraceFacade {
    auto(providers) {
        (0, instrumentation_1.autoTrace)(providers);
    }
    log(message, options = {}) {
        const payload = {
            message,
            level: options.level ?? "info",
        };
        if (options.metadata !== undefined) {
            payload.metadata = options.metadata;
        }
        if (options.timestamp !== undefined) {
            payload.timestamp = options.timestamp;
        }
        const resolvedSpanId = options.spanId === undefined ? (0, context_1.currentSpanId)() : options.spanId;
        return (0, span_1.addArtifact)("log", payload, resolvedSpanId);
    }
    updateSpan(spanId, data) {
        return (0, span_1.updateSpan)(spanId, data);
    }
}
exports.trace = new TraceFacade();
