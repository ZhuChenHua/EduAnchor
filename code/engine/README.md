# EduAnchor Engine

Local, offline textbook-grounded QA engine used by the EduAnchor desktop app.

```bash
uv sync
uv run eduanchor doctor
uv run eduanchor seed
uv run eduanchor ask "什么是机器学习？"
uv run eduanchor eval --all-conditions --out ../results.json
uv run eduanchor serve   # stdio JSON-RPC for Electron
```

Embedding backend defaults to `auto`: it tries BGE-M3 from `FlagEmbedding`
(install with `uv sync --extra models`) and falls back to a deterministic
hash embedder so the system always runs offline without model downloads.

Local LLM is the default: Qwen3-8B through Ollama (`qwen3:8b`, GGUF) or
vLLM (`Qwen/Qwen3-8B-AWQ`, AWQ). Ollama is the default endpoint. Any
OpenAI-compatible endpoint can be selected at runtime:

```bash
uv run eduanchor model show
uv run eduanchor model set --provider ollama --base-url http://127.0.0.1:11434/v1 --name qwen3:8b
uv run eduanchor model set --provider vllm --base-url http://127.0.0.1:8000/v1 --name Qwen/Qwen3-8B-AWQ
uv run eduanchor model set --provider deepseek --api-key "$DEEPSEEK_API_KEY"
uv run eduanchor model test
```

The settings are stored in `$EDUANCHOR_DATA_DIR/model.json` (default
`%LOCALAPPDATA%\EduAnchor\model.json`). Environment variables
`EDUANCHOR_LLM_*` override the file. Without a reachable model, the engine uses
a grounded extractive interpreter.

Tests: `uv run pytest`.
