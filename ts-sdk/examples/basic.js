const { addArtifact, observeRun, observeSpan } = require("../dist");

async function main() {
  await observeRun("coding_agent", async () => {
    await observeSpan("file_read", async () => {
      addArtifact("tool.input", {
        path: "README.md",
      });
      addArtifact("tool.output", {
        bytes: 128,
      });
    });

    await observeSpan("llm_call", async () => {
      addArtifact("llm.prompt", {
        model: "gpt-4o",
        messages: [{ role: "user", content: "hello" }],
      });
      addArtifact("llm.response", {
        content: "world",
      });
    });
  });

  console.log("Telemetry sent to AgentScope.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
