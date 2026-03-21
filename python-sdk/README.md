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

## Auto Instrumentation

```python
from agentscope import auto_instrument

auto_instrument(["openai", "anthropic"])
```

This enables automatic tracing hooks for supported providers.

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
- `observe_span(...)`
- `trace.auto(providers=None)`
- `trace.log(message, level="info", span_id=None, metadata=None, timestamp=None)`
- `trace.update_span(span_id, data)`
- `auto_trace(providers=None)`
- `auto_instrument(providers=None)`
- `coding_agent_run(agent_name="coding_agent")`
- `instrument_coding_agent(fn)`
- `read_file(path, encoding="utf-8")`
- `write_file(path, content, encoding="utf-8")`
- `run_command(command, cwd=None, env=None, check=False, shell=None)`
