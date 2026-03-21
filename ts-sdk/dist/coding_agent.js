"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.codingAgentRun = codingAgentRun;
exports.instrumentCodingAgent = instrumentCodingAgent;
exports.readFile = readFile;
exports.writeFile = writeFile;
exports.runCommand = runCommand;
const node_child_process_1 = require("node:child_process");
const node_fs_1 = require("node:fs");
const node_path_1 = require("node:path");
const node_util_1 = require("node:util");
const instrumentation_1 = require("./instrumentation");
const run_1 = require("./run");
const span_1 = require("./span");
const execAsync = (0, node_util_1.promisify)(node_child_process_1.exec);
const execFileAsync = (0, node_util_1.promisify)(node_child_process_1.execFile);
async function codingAgentRun(fn, options = {}) {
    (0, instrumentation_1.autoInstrument)();
    return (0, run_1.observeRun)("coding_agent", fn, {
        ...options,
        agentName: options.agentName ?? "coding_agent",
    });
}
function instrumentCodingAgent(fn) {
    return async (...args) => {
        return codingAgentRun(() => fn(...args), { agentName: fn.name || "coding_agent" });
    };
}
async function readFile(filePath, encoding = "utf-8") {
    return (0, span_1.observeSpan)("file_read", async () => {
        return node_fs_1.promises.readFile(filePath, { encoding });
    }, {
        metadata: { file_path: filePath },
    });
}
async function writeFile(filePath, content, encoding = "utf-8") {
    const previous = await node_fs_1.promises.readFile(filePath, { encoding }).catch(() => "");
    await (0, span_1.observeSpan)("file_write", async () => {
        await node_fs_1.promises.mkdir((0, node_path_1.dirname)(filePath), { recursive: true });
        await node_fs_1.promises.writeFile(filePath, content, { encoding });
        (0, span_1.addArtifact)("file.diff", {
            file_path: filePath,
            diff: createUnifiedDiff(filePath, previous, content),
        });
        (0, span_1.addArtifact)("file.content", {
            file_path: filePath,
            content,
        });
    }, {
        metadata: { file_path: filePath },
    });
}
async function runCommand(command, options = {}) {
    const resolvedShell = options.shell ?? typeof command === "string";
    const commandText = typeof command === "string" ? command : command.join(" ");
    if (Array.isArray(command) && command.length === 0) {
        throw new Error("runCommand requires at least one command part when command is an array");
    }
    return (0, span_1.observeSpan)("command_exec", async () => {
        try {
            const result = typeof command === "string" || resolvedShell
                ? await execAsync(commandText, {
                    cwd: options.cwd,
                    env: options.env,
                    shell: resolvedShell ? (process.env.SHELL ?? "/bin/sh") : undefined,
                })
                : await execFileAsync(command[0], command.slice(1), {
                    cwd: options.cwd,
                    env: options.env,
                    shell: false,
                });
            const stdout = toText(result.stdout);
            const stderr = toText(result.stderr);
            (0, span_1.addArtifact)("command.stdout", { command: commandText, stdout });
            if (stderr) {
                (0, span_1.addArtifact)("command.stderr", { command: commandText, stderr });
            }
            return {
                command: commandText,
                exitCode: 0,
                stdout,
                stderr,
            };
        }
        catch (error) {
            const stdout = readExecErrorField(error, "stdout");
            const stderr = readExecErrorField(error, "stderr");
            const code = readExecErrorCode(error);
            (0, span_1.addArtifact)("command.stdout", { command: commandText, stdout });
            if (stderr) {
                (0, span_1.addArtifact)("command.stderr", { command: commandText, stderr });
            }
            if (options.check) {
                throw error;
            }
            return {
                command: commandText,
                exitCode: code,
                stdout,
                stderr,
            };
        }
    }, {
        metadata: { command: commandText },
    });
}
function createUnifiedDiff(filePath, previous, next) {
    if (previous === next) {
        return "";
    }
    const before = previous.split("\n");
    const after = next.split("\n");
    const lines = [`--- a/${filePath}`, `+++ b/${filePath}`, "@@"];
    const maxLen = Math.max(before.length, after.length);
    for (let i = 0; i < maxLen; i += 1) {
        const prevLine = before[i];
        const nextLine = after[i];
        if (prevLine === nextLine) {
            if (prevLine !== undefined) {
                lines.push(` ${prevLine}`);
            }
            continue;
        }
        if (prevLine !== undefined) {
            lines.push(`-${prevLine}`);
        }
        if (nextLine !== undefined) {
            lines.push(`+${nextLine}`);
        }
    }
    return `${lines.join("\n")}\n`;
}
function readExecErrorField(error, key) {
    if (error && typeof error === "object" && key in error) {
        const value = error[key];
        return toText(value);
    }
    return "";
}
function readExecErrorCode(error) {
    if (error && typeof error === "object" && "code" in error) {
        const value = error.code;
        if (typeof value === "number" && Number.isFinite(value)) {
            return value;
        }
        if (typeof value === "string") {
            const parsed = Number.parseInt(value, 10);
            if (!Number.isNaN(parsed)) {
                return parsed;
            }
        }
    }
    return 1;
}
function toText(value) {
    if (typeof value === "string") {
        return value;
    }
    if (value instanceof Buffer) {
        return value.toString("utf-8");
    }
    return "";
}
