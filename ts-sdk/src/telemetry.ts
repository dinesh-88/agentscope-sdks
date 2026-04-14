import { createHash, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, hostname, platform } from "node:os";
import { join, resolve } from "node:path";

const SDK_VERSION = "0.1.6";
const DEFAULT_BASE_URL = "http://localhost:8080";
const DEFAULT_TIMEOUT_MS = 1500;
const CONFIG_PATH = join(homedir(), ".agentscope", "config.json");

type TelemetryEventName = "sdk_init" | "run_start" | "run_end";
type TelemetryEnv = "dev" | "prod";

interface TelemetryConfigFile {
  project_id?: string;
  random_seed?: string;
}

interface TelemetryEventPayload {
  event: TelemetryEventName;
  sdk: "ts";
  sdk_version: string;
  runtime: string;
  env: TelemetryEnv;
  project_id: string;
  timestamp: string;
  error_type?: string;
}

export class SdkTelemetry {
  private baseUrl: string;
  private timeoutMs: number;
  private enabled: boolean;
  private projectId: string | null;

  constructor() {
    this.baseUrl = (
      process.env.AGENTSCOPE_API_BASE
      ?? process.env.AGENTSCOPE_API
      ?? DEFAULT_BASE_URL
    ).replace(/\/$/, "");
    this.timeoutMs = DEFAULT_TIMEOUT_MS;
    this.enabled = parseBoolean(process.env.AGENTSCOPE_TELEMETRY_ENABLED, false);
    this.projectId = null;
  }

  configure(options: { baseUrl?: string; timeoutMs?: number; enabled?: boolean } = {}): void {
    if (options.baseUrl) {
      this.baseUrl = options.baseUrl.replace(/\/$/, "");
    }
    if (typeof options.timeoutMs === "number" && Number.isFinite(options.timeoutMs) && options.timeoutMs > 0) {
      this.timeoutMs = options.timeoutMs;
    }
    if (typeof options.enabled === "boolean") {
      this.enabled = options.enabled;
    }
  }

  capture(event: TelemetryEventName, errorType?: string): void {
    if (!this.enabled) {
      return;
    }

    const projectId = this.ensureProjectId();
    const payload: TelemetryEventPayload = {
      event,
      sdk: "ts",
      sdk_version: SDK_VERSION,
      runtime: `node/${process.version}`,
      env: resolveEnv(),
      project_id: projectId,
      timestamp: new Date().toISOString(),
    };

    if (errorType) {
      payload.error_type = errorType;
    }

    void this.send(payload);
  }

  projectHash(): string {
    return this.ensureProjectId();
  }

  private async send(payload: TelemetryEventPayload): Promise<void> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      await fetch(`${this.baseUrl}/v1/telemetry`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
    } catch {
      // Telemetry failures must never affect SDK behavior.
    } finally {
      clearTimeout(timeout);
    }
  }

  private ensureProjectId(): string {
    if (this.projectId) {
      return this.projectId;
    }

    const config = readTelemetryConfig();
    if (isSha256Hex(config.project_id)) {
      this.projectId = config.project_id;
      return this.projectId;
    }

    const seed = isNonEmptyString(config.random_seed)
      ? config.random_seed
      : randomBytes(16).toString("hex");
    const machineId = resolveMachineId();
    const repoPath = resolve(process.cwd());
    const projectId = sha256Hex(`${machineId}|${repoPath}|${seed}`);

    writeTelemetryConfig({
      ...config,
      random_seed: seed,
      project_id: projectId,
    });

    this.projectId = projectId;
    return this.projectId;
  }
}

let telemetrySingleton: SdkTelemetry | null = null;

export function getSdkTelemetry(options: { baseUrl?: string; timeoutMs?: number; enabled?: boolean } = {}): SdkTelemetry {
  if (!telemetrySingleton) {
    telemetrySingleton = new SdkTelemetry();
  }
  telemetrySingleton.configure(options);
  return telemetrySingleton;
}

function resolveMachineId(): string {
  const candidates = ["/etc/machine-id", "/var/lib/dbus/machine-id"];
  for (const candidate of candidates) {
    try {
      if (existsSync(candidate)) {
        const content = readFileSync(candidate, "utf8").trim();
        if (content) {
          return content;
        }
      }
    } catch {
      // Ignore unreadable machine ID files.
    }
  }
  return `${hostname()}|${platform()}`;
}

function resolveEnv(): TelemetryEnv {
  const raw = (
    process.env.AGENTSCOPE_ENV
    ?? process.env.AGENTSCOPE_ENVIRONMENT
    ?? process.env.NODE_ENV
    ?? "dev"
  ).trim().toLowerCase();
  return raw === "prod" || raw === "production" ? "prod" : "dev";
}

function parseBoolean(value: string | undefined, defaultValue: boolean): boolean {
  if (value == null) {
    return defaultValue;
  }
  const normalized = value.trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
}

function sha256Hex(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function readTelemetryConfig(): TelemetryConfigFile {
  try {
    if (!existsSync(CONFIG_PATH)) {
      return {};
    }
    const raw = readFileSync(CONFIG_PATH, "utf8");
    const parsed = JSON.parse(raw) as TelemetryConfigFile;
    return parsed ?? {};
  } catch {
    return {};
  }
}

function writeTelemetryConfig(config: TelemetryConfigFile): void {
  try {
    mkdirSync(join(homedir(), ".agentscope"), { recursive: true, mode: 0o700 });
    writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), { encoding: "utf8", mode: 0o600 });
  } catch {
    // Best-effort persistence only.
  }
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isSha256Hex(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}
