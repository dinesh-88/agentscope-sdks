"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.flush = exports.TelemetryExporter = exports.observeSpan = exports.addArtifact = exports.observeRun = exports.AgentScopeClient = void 0;
const instrumentation_1 = require("./instrumentation");
var client_1 = require("./client");
Object.defineProperty(exports, "AgentScopeClient", { enumerable: true, get: function () { return client_1.AgentScopeClient; } });
var run_1 = require("./run");
Object.defineProperty(exports, "observeRun", { enumerable: true, get: function () { return run_1.observeRun; } });
var span_1 = require("./span");
Object.defineProperty(exports, "addArtifact", { enumerable: true, get: function () { return span_1.addArtifact; } });
Object.defineProperty(exports, "observeSpan", { enumerable: true, get: function () { return span_1.observeSpan; } });
var exporter_1 = require("./exporter");
Object.defineProperty(exports, "TelemetryExporter", { enumerable: true, get: function () { return exporter_1.TelemetryExporter; } });
Object.defineProperty(exports, "flush", { enumerable: true, get: function () { return exporter_1.flushPendingExports; } });
__exportStar(require("./types"), exports);
__exportStar(require("./instrumentation"), exports);
(0, instrumentation_1.instrumentFetch)();
