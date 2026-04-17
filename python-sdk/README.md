# AgentScope Python SDK

Python SDK for AgentScope telemetry, tracing, and instrumentation.

## Install

```bash
pip install agentscope-sdk
```

## Quick Start

```python
from agentscope import observe_run, observe_span, trace

with observe_run("coding_agent", agent_name="demo"):
    with observe_span("llm_call", provider="openai", model="gpt-4o"):
        trace.log("sending prompt", level="info")
```

Set `AGENTSCOPE_API_BASE=http://localhost:8080` and `AGENTSCOPE_API_KEY=...` as needed.

## Anonymous SDK Telemetry (Optional)

Telemetry is sent only after explicit consent.

On first interactive SDK run, AgentScope prompts:

```text
AgentScope Telemetry

We collect anonymous usage data to:
- improve debugging insights
- understand feature usage

We DO NOT collect:
- prompts
- outputs
- personal data

Enable telemetry? (y/N)
```

Consent is persisted in `~/.agentscope/config.json`:

```json
{
  "telemetry_enabled": true,
  "consent_timestamp": "2026-04-06T10:00:00Z"
}
```

Override options:

```bash
export AGENTSCOPE_TELEMETRY=on   # or off
```

```python
import agentscope

agentscope.init(telemetry=True)   # or False
```

CLI consent management:

```bash
agentscope telemetry enable
agentscope telemetry disable
```

When enabled, the SDK sends only anonymous events (`sdk_init`, `run_start`, `run_end`) to `POST /v1/telemetry` using an anonymized `project_id` persisted at `~/.agentscope/config.json`. Prompt/output content and user payloads are never sent by this channel.

## Auto Instrumentation

```python
from agentscope import auto_instrument

auto_instrument(["openai", "anthropic"])
```

This enables automatic provider tracing, orchestration boundary detection, and
context propagation.

Default orchestration detectors:
- HTTP ASGI (`FastAPI`/`Starlette`) request boundary
- `gRPC` server interceptors
- `Celery` task execution boundary
- `kafka-python` consumer poll boundary (best-effort)

Default propagation:
- HTTP headers via `requests`
- Kafka message headers via `kafka-python` producer

Each boundary creates/continues one root orchestration run so agent runs inside
that boundary share one `trace_id` automatically.

Disable orchestration auto-detection if needed:

```python
auto_instrument(["openai"], orchestration=False)
```

Choose specific transports:

```python
auto_instrument(["openai"], orchestration=["http", "grpc"])
```

Disable propagation injection:

```python
auto_instrument(["openai"], propagation=False)
```

## Coding-Agent Helpers

```python
from agentscope import coding_agent_run, read_file, run_command, write_file

with coding_agent_run(agent_name="codebot"):
    content = read_file("README.md")
    write_file("notes.txt", content)
    result = run_command("echo done")
```

## API

- `observe_run(...)`
  - Cross-run linkage params: `trace_id=...`, `parent_run_id=...`, `root_run_id=...`
- `observe_span(...)`
- `trace.auto(providers=None)`
- `trace.log(message, level="info", span_id=None, metadata=None, timestamp=None)`
- `trace.update_span(span_id, data)`
- `auto_trace(providers=None)`
- `auto_instrument(providers=None, orchestration="auto", propagation=True, orchestration_workflow_name="orchestration_auto_trace", orchestration_agent_name="orchestrator")`
- `coding_agent_run(agent_name="coding_agent")`
- `instrument_coding_agent(fn)`
- `read_file(path, encoding="utf-8")`
- `write_file(path, content, encoding="utf-8")`
- `run_command(command, cwd=None, env=None, check=False, shell=None)`

## License

`agentscope-sdk` is licensed under the MIT License. See the `LICENSE` file in the repository root for details.
