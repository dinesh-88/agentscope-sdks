# AgentScope TypeScript SDK

Node.js SDK for instrumenting runs, spans, and artifacts and exporting them to the AgentScope ingestion API.

## Install

```bash
npm install
npm run build
```

## Usage

```ts
import { addArtifact, observeRun, observeSpan } from "@agentscope/sdk";

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
});
```

Set `AGENTSCOPE_API=http://localhost:8080` if the API is not running on the default host.

## Example Script

```bash
npm install
npm run example
```

This runs [examples/basic.js](/Users/dineshpriyashantha/Documents/agentscope/packages/ts-sdk/examples/basic.js), which emits a run with nested spans and artifacts to the local AgentScope API.

## API

- `observeRun(workflowName, fn, options?)`
- `observeSpan(name, fn, options?)`
- `addArtifact(kind, payload)`
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
