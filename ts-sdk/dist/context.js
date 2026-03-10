"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getRunState = getRunState;
exports.withRunState = withRunState;
exports.currentSpanId = currentSpanId;
exports.withSpanContext = withSpanContext;
const node_async_hooks_1 = require("node:async_hooks");
const contextStorage = new node_async_hooks_1.AsyncLocalStorage();
function getRunState() {
    return contextStorage.getStore();
}
function withRunState(state, fn) {
    return contextStorage.run(state, fn);
}
function currentSpanId() {
    const state = getRunState();
    if (!state || state.spanStack.length === 0) {
        return null;
    }
    return state.spanStack[state.spanStack.length - 1] ?? null;
}
async function withSpanContext(spanId, fn) {
    const state = getRunState();
    if (!state) {
        throw new Error("observeSpan must be called inside observeRun");
    }
    const nextState = {
        ...state,
        spanStack: [...state.spanStack, spanId],
    };
    return contextStorage.run(nextState, fn);
}
