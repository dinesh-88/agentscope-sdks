import { exec, execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import { dirname } from "node:path";
import { promisify } from "node:util";

import { autoInstrument } from "./instrumentation";
import { observeRun } from "./run";
import { addArtifact, observeSpan } from "./span";
import type { CommandResult, ObserveRunOptions } from "./types";

const execAsync = promisify(exec);
const execFileAsync = promisify(execFile);

export interface RunCommandOptions {
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  check?: boolean;
  shell?: boolean;
}

export async function codingAgentRun<T>(
  fn: () => Promise<T> | T,
  options: Omit<ObserveRunOptions, "agentName"> & { agentName?: string } = {},
): Promise<T> {
  autoInstrument();
  return observeRun("coding_agent", fn, {
    ...options,
    agentName: options.agentName ?? "coding_agent",
  });
}

export function instrumentCodingAgent<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult> | TResult,
): (...args: TArgs) => Promise<TResult> {
  return async (...args: TArgs) => {
    return codingAgentRun(() => fn(...args), { agentName: fn.name || "coding_agent" });
  };
}

export async function readFile(filePath: string, encoding: BufferEncoding = "utf-8"): Promise<string> {
  return observeSpan("file_read", async () => {
    return fs.readFile(filePath, { encoding });
  }, {
    metadata: { file_path: filePath },
  });
}

export async function writeFile(
  filePath: string,
  content: string,
  encoding: BufferEncoding = "utf-8",
): Promise<void> {
  const previous = await fs.readFile(filePath, { encoding }).catch(() => "");

  await observeSpan("file_write", async () => {
    await fs.mkdir(dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, content, { encoding });

    addArtifact("file.diff", {
      file_path: filePath,
      diff: createUnifiedDiff(filePath, previous, content),
    });
    addArtifact("file.content", {
      file_path: filePath,
      content,
    });
  }, {
    metadata: { file_path: filePath },
  });
}

export async function runCommand(
  command: string | string[],
  options: RunCommandOptions = {},
): Promise<CommandResult> {
  const resolvedShell = options.shell ?? typeof command === "string";
  const commandText = typeof command === "string" ? command : command.join(" ");
  if (Array.isArray(command) && command.length === 0) {
    throw new Error("runCommand requires at least one command part when command is an array");
  }

  return observeSpan("command_exec", async () => {
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
      addArtifact("command.stdout", { command: commandText, stdout });
      if (stderr) {
        addArtifact("command.stderr", { command: commandText, stderr });
      }

      return {
        command: commandText,
        exitCode: 0,
        stdout,
        stderr,
      };
    } catch (error) {
      const stdout = readExecErrorField(error, "stdout");
      const stderr = readExecErrorField(error, "stderr");
      const code = readExecErrorCode(error);

      addArtifact("command.stdout", { command: commandText, stdout });
      if (stderr) {
        addArtifact("command.stderr", { command: commandText, stderr });
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

function createUnifiedDiff(filePath: string, previous: string, next: string): string {
  if (previous === next) {
    return "";
  }

  const before = previous.split("\n");
  const after = next.split("\n");
  const lines: string[] = [`--- a/${filePath}`, `+++ b/${filePath}`, "@@"];

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

function readExecErrorField(error: unknown, key: "stdout" | "stderr"): string {
  if (error && typeof error === "object" && key in error) {
    const value = (error as Record<string, unknown>)[key];
    return toText(value);
  }
  return "";
}

function readExecErrorCode(error: unknown): number {
  if (error && typeof error === "object" && "code" in error) {
    const value = (error as Record<string, unknown>).code;
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

function toText(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value instanceof Buffer) {
    return value.toString("utf-8");
  }
  return "";
}
