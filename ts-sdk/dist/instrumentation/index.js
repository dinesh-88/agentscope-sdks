"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.instrumentFetch = void 0;
exports.autoTrace = autoTrace;
exports.autoInstrument = autoInstrument;
exports.resetAutoInstrumentation = resetAutoInstrumentation;
const fetch_1 = require("./fetch");
Object.defineProperty(exports, "instrumentFetch", { enumerable: true, get: function () { return fetch_1.instrumentFetch; } });
let restoreInstrumentation = null;
function autoTrace(providers) {
    if (restoreInstrumentation) {
        return;
    }
    restoreInstrumentation = (0, fetch_1.instrumentFetch)({ providers });
}
function autoInstrument(providers) {
    autoTrace(providers);
}
function resetAutoInstrumentation() {
    if (!restoreInstrumentation) {
        return;
    }
    restoreInstrumentation();
    restoreInstrumentation = null;
}
