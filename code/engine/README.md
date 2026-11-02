# EduAnchor Engine

Local, offline textbook-grounded QA engine used by the EduAnchor desktop app.

```bash
uv sync
uv run eduanchor doctor
uv run eduanchor seed
uv run eduanchor ask "什么是机器学习？"
uv run eduanchor eval --all-conditions --out ../results.json  # C1-C7
uv run eduanchor serve   # stdio JSON-RPC for Electron
```

Embedding backend defaults to `auto`: it tries BGE-M3 from `FlagEmbedding`
(install with `uv sync --extra models`) and falls back to a deterministic
hash embedder so the system always runs offline without model downloads.

The default is the built-in Qwen3-8B Q4_K_M file served by llama.cpp at
`http://127.0.0.1:8081/v1`. Start it from the repository root with
`pwsh ../scripts/start-model.ps1`; the Electron app does this automatically.
Ollama (`qwen3:8b`) and vLLM (`Qwen/Qwen3-8B-AWQ`) are optional. Any
OpenAI-compatible endpoint can be selected at runtime:

```bash
uv run eduanchor model show
uv run eduanchor model set --provider llamacpp --base-url http://127.0.0.1:8081/v1 --name qwen3-8b
uv run eduanchor model set --provider ollama --base-url http://127.0.0.1:11434/v1 --name qwen3:8b
uv run eduanchor model set --provider vllm --base-url http://127.0.0.1:8000/v1 --name Qwen/Qwen3-8B-AWQ
uv run eduanchor model set --provider deepseek --api-key "$DEEPSEEK_API_KEY"
uv run eduanchor model test
```

The settings are stored in `$EDUANCHOR_DATA_DIR/model.json` (default
`%LOCALAPPDATA%\EduAnchor\model.json`). Environment variables
`EDUANCHOR_LLM_*` override the file. `EDUANCHOR_TEMPERATURE=0` gives greedy
decoding; the paper runs use temperature 0 and seed 42. Without a reachable
model, the engine uses a grounded extractive interpreter.

Tests: `uv run pytest`.
