# AgentScope TypeScript SDK

Node.js SDK for instrumenting runs, spans, and artifacts and exporting them to the AgentScope ingestion API.

## Install

```bash
npm install
npm run build
```

## Usage

```ts
import { addArtifact, autoInstrument, observeRun, observeSpan, trace } from "@agentscope/sdk";

autoInstrument(["openai", "anthropic"]);

await observeRun("coding_agent", async () => {
  await observeSpan("file_read", async () => {
    // file read logic
  });

  await observeSpan("llm_call", async () => {
    addArtifact("llm.prompt", {
      model: "gpt-4o",
      messages: [{ role: "user", content: "hello" }],
    });
  });

  trace.log("run step finished", { level: "info" });
});
```

Set `AGENTSCOPE_API_BASE=http://localhost:8080` if the API is not running on the default host.

## Anonymous SDK Telemetry (Optional)

SDK usage telemetry is disabled by default. To opt in, set:

```bash
export AGENTSCOPE_TELEMETRY_ENABLED=true
```

When enabled, the SDK sends only anonymous events (`sdk_init`, `run_start`, `run_end`) to `POST /v1/telemetry` with an anonymized `project_id` stored in `~/.agentscope/config.json`. Prompt/output content and user payloads are never sent by this channel.

## Example Script

```bash
npm install
npm run example
```

This runs `examples/basic.js`, which emits a run with nested spans and artifacts to the local AgentScope API.

## API

- `observeRun(workflowName, fn, options?)`
  - Cross-run linkage options in `options`: `traceId`, `parentRunId`, `rootRunId`
- `observeSpan(name, fn, options?)`
- `addArtifact(kind, payload, spanId?)`
- `trace.auto(providers?)`
- `trace.log(message, options?)`
- `trace.updateSpan(spanId, data)`
- `autoTrace(providers?)`
- `autoInstrument(providers?)`
- `codingAgentRun(fn, options?)`
- `instrumentCodingAgent(fn)`
- `readFile(filePath, encoding?)`
- `writeFile(filePath, content, encoding?)`
- `runCommand(command, options?)`
- `flush()`

## Fetch Instrumentation

Phase two includes fetch auto-instrumentation:

```ts
import { instrumentFetch, observeRun } from "@agentscope/sdk";

const restoreFetch = instrumentFetch();

await observeRun("coding_agent", async () => {
  await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hello" }],
    }),
  });
});

restoreFetch();
```

OpenAI-compatible requests are detected by URL and JSON payload shape. Prompt and response bodies are captured as `llm.prompt` and `llm.response` artifacts.
