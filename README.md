# EduAnchor

**English** | [简体中文](README.zh-CN.md)

**Offline, textbook-grounded multi-agent interpretation platform** — an Electron desktop app backed by a local Python RAG/agent engine. This repository is the reference implementation for an academic paper on textbook-anchored, evidence-grounded learning support.

> The model reads only the textbook you give it. Every answer carries page-level provenance, and when the textbook does not cover a question, the system refuses instead of guessing.

## Why a desktop app

- **Privacy**: textbooks and student questions never leave the machine.
- **Zero deployment**: one full offline package (or a small code-only installer); no server, domain, or cloud GPU.
- **Offline demos**: works with networking disabled.
- **Reproducibility**: the same artifact is used for the demo, the user study, and the paper.
- **Consumer hardware**: built-in Qwen3-8B Q4_K_M via llama.cpp; AWQ via vLLM is optional.

The renderer, Electron main process, and Python engine all run locally. The engine is a child process speaking newline-delimited JSON-RPC over stdio; the bundled model server binds to **loopback only**.

## Repository layout

```
code/
  engine/        Python 3.11+ engine, managed by uv
    src/eduanchor/
      pdf_parser.py chunker.py cards.py      # ingestion + anchors
      embeddings.py bm25.py retriever.py     # hybrid retrieval
      agents.py pipeline.py                  # planner/interpreter/verifier + boundary policy
      evaluation.py rpc.py cli.py            # eval harness, stdio RPC, CLI
    tests/                                   # pytest suite
    packaging/                               # PyInstaller build
  desktop/       Electron 33 + Vue 3 + Vite + TypeScript
  scripts/       dev / build-engine / package PowerShell scripts
docs/            deployment guides (English + Chinese)
```

## Quick start

Requirements: **uv**, **Node.js 20+**, Windows 10/11 (macOS/Linux should work with minor packaging changes).

```powershell
# 1) Python engine
cd code/engine
uv sync
uv run eduanchor seed            # import the bundled sample textbook
uv run eduanchor doctor          # show LLM/embedder/status

# CLI/eval only: start the bundled model in a second terminal
pwsh ../scripts/start-model.ps1

# 2) Desktop app
cd ../desktop
npm install
npm run dev
```

The app starts the engine and, when the bundled files are present, the built-in llama.cpp model server. If no model is available, the engine uses a grounded **extractive interpreter** and a deterministic hash embedder, so the full UI still works.

### Import your own textbook

Use **导入教材** in the sidebar (PDF / Markdown / TXT). PDFs need a text layer; scanned books are out of scope. Markdown can use `<!-- page: N -->` markers to preserve page numbers.

## Choose a model

Open **Model settings** in the sidebar. The engine supports any OpenAI-compatible chat endpoint. Configuration is stored locally in `%LOCALAPPDATA%\EduAnchor\model.json`; environment variables override the file.

| Provider | Base URL | Default model | API key |
| --- | --- | --- | --- |
| Built-in llama.cpp (default) | `http://127.0.0.1:8081/v1` | `qwen3-8b` | no |
| Ollama (local, GGUF) | `http://127.0.0.1:11434/v1` | `qwen3:8b` | no |
| vLLM (local, AWQ) | `http://127.0.0.1:8000/v1` | `Qwen/Qwen3-8B-AWQ` | no |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | yes |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | yes |
| DashScope (Qwen) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | yes |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | yes |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen3-8B` | yes |
| Custom | any OpenAI-compatible `/v1` | your model | optional |

The **Test connection** button performs a short chat request before saving. API keys are never returned to the renderer or written to logs; they are stored in the local `model.json` file (plain text on disk).

### Built-in default: Qwen3-8B Q4_K_M

The project ships the quantized model and its runtime, so the application does not need Ollama:

- `models/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf` (about 5.0 GB)
- `runtime/llama/llama-server.exe` plus its DLLs

Both directories are excluded from Git because of their size, but they are part of the local project and the full offline package. `npm run dev` starts `llama-server` at `http://127.0.0.1:8081/v1` with alias `qwen3-8b`; the default provider is `llamacpp`. To refresh the weights from ModelScope:

```powershell
uv tool install modelscope
modelscope download --model Qwen/Qwen3-8B-GGUF --local_dir .\models\Qwen3-8B-GGUF
```

To build the full offline distribution (model plus runtime):

```powershell
npm run dist:full
```

This produces a ZIP in `code/desktop/release-full/`. A ZIP is used because the bundled model exceeds the practical NSIS size limit. `npm run dist` still builds the small code-only installer.

### Optional local backends

**AWQ via vLLM.** Download the AWQ build and serve it on Linux/WSL2:

```powershell
modelscope download --model Qwen/Qwen3-8B-AWQ --local_dir .\models\Qwen3-8B-AWQ
vllm serve .\models\Qwen3-8B-AWQ --port 8000 --served-model-name Qwen/Qwen3-8B-AWQ
```

Then set the Base URL to `http://127.0.0.1:8000/v1` and the model name to `Qwen/Qwen3-8B-AWQ`.

**Ollama.** If you prefer Ollama, pull `qwen3:8b` or import the same GGUF:

```powershell
ollama pull qwen3:8b
ollama serve
```

Then select the Ollama preset. Ollama and vLLM are options, not requirements.

### Remote provider APIs

Pick a preset, paste the API key, test, and save. **A remote provider receives the retrieved textbook snippets**; use it only when the course policy allows sending excerpted material to that vendor. The interface labels the active endpoint as local or remote. On shared machines, prefer environment variables or a separate OS account for the key.

Environment overrides:

```powershell
$env:EDUANCHOR_LLM_PROVIDER = "llamacpp"      # llamacpp | ollama | vllm | openai | deepseek | dashscope | custom
$env:EDUANCHOR_LLM_BASE_URL = "http://127.0.0.1:8081/v1"
$env:EDUANCHOR_LLM_MODEL = "qwen3-8b"
$env:EDUANCHOR_LLM_API_KEY = "..."           # only for remote providers
```

### Optional BGE-M3 embeddings

```powershell
cd code/engine
uv sync --extra models
$env:EDUANCHOR_EMBED_BACKEND = "bge"
```

`auto` tries BGE-M3 and falls back to the hash embedder. Changing the embedding backend automatically invalidates and rebuilds the vector index (the backend name is stored in the index).

## CLI

```powershell
cd code/engine
uv run eduanchor ask "什么是机器学习？"
uv run eduanchor ask "什么是过拟合？" --mode socratic
uv run eduanchor model show               # show the active provider
uv run eduanchor model test               # test the configured endpoint
uv run eduanchor model set --provider deepseek --api-key $env:DEEPSEEK_API_KEY
uv run eduanchor cards                    # list knowledge cards
uv run eduanchor eval --all-conditions --out ../results.json
uv run eduanchor serve                    # stdio JSON-RPC (used by Electron)
```

`eval` runs the C1–C5 ablation: bare model, dense RAG, hybrid retrieval, multi-agent verification, and full anchor enforcement. It writes per-question JSON and LaTeX tables.

## Tests

```powershell
cd code/engine
uv run pytest -q
uv run ruff check src tests
```

## Build the executable + installer

```powershell
cd code
pwsh ./scripts/build-engine.ps1     # PyInstaller onedir -> engine/dist/eduanchor-engine
pwsh ./scripts/package.ps1          # build engine + electron-builder
```

Outputs: `code/desktop/release/EduAnchor-Setup-*.exe` and `EduAnchor-Portable-*.exe`.

If the Electron binary download is slow or blocked, set mirrors before packaging:

```powershell
$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
$env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
npm run dist
```

`signAndEditExecutable` is disabled in `package.json` so packaging works without
a code-signing certificate or Windows symbolic-link privileges. Enable it (and
configure a certificate) for a signed public release.

The packaged app expects the engine at `resources/engine/eduanchor-engine.exe`, which `package.ps1` arranges through `extraResources`. For the classroom build with the model and runtime, run `npm run dist:full` in `code/desktop`; it writes a ZIP to `release-full/`.

## Academic manuscript

The conference manuscript, Chinese original, figures, and submission materials are maintained outside this repository and are not tracked here. The engine still supports `--latex-dir <dir>` on `eduanchor eval` if you want to export LaTeX tables locally.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for packaging, offline model distribution, code signing, and troubleshooting.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `EDUANCHOR_DATA_DIR` | `%LOCALAPPDATA%\EduAnchor` | SQLite DB, indexes, sessions |
| `EDUANCHOR_LLM_PROVIDER` | `llamacpp` | `llamacpp`, `ollama`, `vllm`, `openai`, `deepseek`, `dashscope`, `moonshot`, `siliconflow`, `custom` |
| `EDUANCHOR_LLM_BASE_URL` | `http://127.0.0.1:8081/v1` | OpenAI-compatible endpoint |
| `EDUANCHOR_LLM_MODEL` | `qwen3-8b` | Model name |
| `EDUANCHOR_LLM_API_KEY` | empty | Remote provider key |
| `EDUANCHOR_LLM_TIMEOUT` | `180` | Seconds |
| `EDUANCHOR_EMBED_BACKEND` | `auto` | `auto`, `bge`, or `hash` |
| `EDUANCHOR_EMBED_MODEL` | `BAAI/bge-m3` | Local/remote model path |
| `EDUANCHOR_COVERAGE_THRESHOLD` | `0.15` | Coverage threshold for hash embeddings |

## Scope

- Text-only; no OCR, figures, formulas, or tables.
- No large-scale training; Qwen3-8B is used frozen, optionally with LoRA as a future extension.
- Not a general assistant: refusing out-of-textbook questions is a feature, not a failure.
