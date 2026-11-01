# Deployment Guide

**English** | [简体中文](DEPLOYMENT.zh-CN.md)

This document describes how to package EduAnchor as a Windows desktop application, distribute it offline, and verify the result.

## 1. What gets shipped

```
EduAnchor-Setup-x.y.z-x64.exe       NSIS installer
EduAnchor-Portable-x.y.z-x64.exe    single-file portable launcher
```

The installer contains:

- Electron runtime and the Vue renderer (`dist/`).
- Electron main/preload code (`dist-electron/`).
- A PyInstaller `onedir` Python engine at `resources/engine/`
  (`eduanchor-engine.exe` + `_internal/`).

The installer **does not** contain a language model or the BGE-M3 weights.
Qwen3-8B is expected to be served locally through an OpenAI-compatible
endpoint (Ollama or llama.cpp). Without a model, the engine runs the grounded
extractive interpreter; without BGE-M3 it uses a deterministic hash embedder.
Both fallbacks are intentional and keep the installer around 120 MB.

## 2. Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Windows | 10/11 x64 | Build and target platform |
| Node.js | 20+ | Renderer and Electron tooling |
| uv | 0.8+ | Python engine, lockfile-based |
| Python | 3.11+ | uv can install it automatically |
| Ollama / llama.cpp / vLLM | optional | Local Qwen3-8B endpoint (GGUF or AWQ) |

## 3. Development run

```powershell
cd code/engine
uv sync
uv run eduanchor seed
uv run eduanchor doctor

cd ../desktop
npm install
npm run dev
```

Electron starts the engine from `.venv\Scripts\eduanchor-rpc.exe` when present;
otherwise it runs `uv run eduanchor-rpc`.

## 4. Build the Python engine

```powershell
cd code
pwsh ./scripts/build-engine.ps1
```

Equivalent command:

```powershell
cd code/engine
uv sync
uv run --with pyinstaller pyinstaller packaging/eduanchor-engine.spec --noconfirm --clean
```

Output: `code/engine/dist/eduanchor-engine/`.

The spec bundles `src/eduanchor/data` (sample textbook and pilot QA set) and
excludes `torch`, `FlagEmbedding`, `onnxruntime`, and other optional heavy
dependencies. Verify the bundle without Electron (run from the repository root):

```powershell
$env:EDUANCHOR_DATA_DIR = "$env:TEMP\eduanchor-engine-smoke"
'{"jsonrpc":"2.0","id":1,"method":"system.ping"}' |
  .\code\engine\dist\eduanchor-engine\eduanchor-engine.exe
```

### Optional: BGE-M3 embeddings

The default bundle uses the hash embedder. To ship BGE-M3:

1. Install the model extra: `cd code/engine && uv sync --extra models`.
2. Download `BAAI/bge-m3` into a local cache and set `HF_HOME` on the target.
3. Rebuild the engine **without** the `FlagEmbedding` / `torch` exclusions in
   `packaging/eduanchor-engine.spec`.
4. Set `EDUANCHOR_EMBED_BACKEND=bge` (or `auto`) for the app.

Expect a much larger bundle (PyTorch + model weights). For a lightweight demo,
keep the hash fallback and document the configuration honestly.

## 5. Build the desktop installer

```powershell
cd code/desktop
npm install
npm run build          # Vite renderer + tsc main/preload
npm run dist           # electron-builder
```

If GitHub downloads are blocked, use mirrors:

```powershell
$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
$env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
npm run dist
```

`build.win.signAndEditExecutable` is set to `false` so packaging works without
a certificate or the Windows symbolic-link privilege. For a signed release,
remove that flag and configure signing:

```powershell
$env:CSC_LINK = "C:\path\to\certificate.pfx"
$env:CSC_KEY_PASSWORD = "***"
npm run dist
```

Artifacts:

```
code/desktop/release/EduAnchor-Setup-0.1.0-x64.exe
code/desktop/release/EduAnchor-Portable-0.1.0-x64.exe
```

## 6. Verify the packaged app

A built-in smoke mode checks the full chain: Electron main → preload client →
Python engine → sample import → grounded answer.

```powershell
$env:EDUANCHOR_SMOKE = "1"
$env:EDUANCHOR_DATA_DIR = "$env:TEMP\eduanchor-smoke"
.\code\desktop\release\win-unpacked\EduAnchor.exe
```

Expected: the process exits with code 0 and
`$env:EDUANCHOR_DATA_DIR\eduanchor.sqlite3` contains one session and six cards.
Run this before every release; it catches a missing engine binary, a broken
JSON-RPC handshake, or a packaging path error.

## 7. Offline model distribution

EduAnchor itself never downloads models. Choose one of these deployment modes:

### A. Preinstalled Ollama / vLLM (simplest)

On the target machine, once with network:

```powershell
ollama pull qwen3:8b
ollama serve
```

For mainland China, download the official quantized build from ModelScope:

```powershell
uv tool install modelscope
modelscope download --model Qwen/Qwen3-8B-GGUF --local_dir .\models\Qwen3-8B-GGUF
```

Then import it into Ollama from the Q4_K_M GGUF (adjust the filename if needed):

```powershell
@"
FROM ./models/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf
PARAMETER num_ctx 8192
"@ | Set-Content Modelfile
ollama create qwen3:8b -f Modelfile
ollama serve
```

For the AWQ build, download it and serve with vLLM on Linux/WSL2:

```powershell
modelscope download --model Qwen/Qwen3-8B-AWQ --local_dir .\models\Qwen3-8B-AWQ
vllm serve .\models\Qwen3-8B-AWQ --port 8000 --served-model-name Qwen/Qwen3-8B-AWQ
$env:EDUANCHOR_LLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:EDUANCHOR_LLM_MODEL = "Qwen/Qwen3-8B-AWQ"
```

For a fully offline lab image, pre-populate the Ollama model store or bake
the model into the image.

### B. Bundled llama.cpp server

Ship a `llama-server.exe` plus a GGUF Qwen3-8B file (Q4_K_M) and start it
before EduAnchor:

```powershell
llama-server -m qwen3-8b-q4_k_m.gguf --port 8080
$env:EDUANCHOR_LLM_BASE_URL = "http://127.0.0.1:8080/v1"
```

Keep the model outside the installer to avoid a multi-GB package.

### C. Remote vendor API

The same **Model settings** dialog accepts any OpenAI-compatible endpoint. Built-in
presets include OpenAI, DeepSeek, DashScope (Qwen), Moonshot, and SiliconFlow.
The active configuration is stored in `%LOCALAPPDATA%\EduAnchor\model.json`
(or `EDUANCHOR_DATA_DIR/model.json`); environment variables override it.

A remote provider receives the retrieved textbook snippets. Use it only when the
course or copyright policy permits sending excerpts to that vendor. API keys are
never returned to the renderer or logged, but they are stored as plain text in
`model.json`; use environment variables or a dedicated OS account on shared
machines.

### D. Hash fallback (no model)

Useful for UI review, grading, and offline demos. Answers are extractive and
strictly quoted; C1 is unavailable because it needs a generative model.

## 8. First run and data locations

Default data directory:

```
%LOCALAPPDATA%\EduAnchor\
  eduanchor.sqlite3      documents, chunks, cards, sessions
  index\*.npz            chunk vectors, keyed by embedding backend
  sessions\              reserved
```

Override with `EDUANCHOR_DATA_DIR`. The directory is safe to back up; deleting
it only removes imported textbooks and session history.

## 9. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `engine start timeout` | Engine binary missing or crashed. Run `eduanchor-engine.exe` manually and check stderr. |
| App opens but every call fails | `resources/engine` not copied. Check `electron-builder.yml`/`package.json` `extraResources`. |
| `ERR_ELECTRON_BUILDER_CANNOT_EXECUTE` while downloading Electron | Set `ELECTRON_MIRROR` and `ELECTRON_BUILDER_BINARIES_MIRROR`. |
| 7-Zip "Cannot create symbolic link" | Windows lacks symlink privilege while extracting winCodeSign. Keep `signAndEditExecutable=false` or run packaging as administrator. |
| Installer is ~500 MB+ | Optional model dependencies were bundled. Check the PyInstaller `excludes`. |
| Answers are always refused | The query is outside the textbook, or the coverage threshold is too high for the active embedder. Tune `EDUANCHOR_COVERAGE_THRESHOLD` (hash default 0.15; BGE-M3 0.36). |
| LLM never activates | Check `curl http://127.0.0.1:11434/v1/models`; set `EDUANCHOR_LLM_BASE_URL` / `EDUANCHOR_LLM_MODEL`. |
| PDF import fails | The PDF has no text layer (scanned). OCR is out of scope. |

## 10. Release checklist

- [ ] `uv run pytest -q` and `uv run ruff check src tests` pass.
- [ ] `npm run typecheck` passes.
- [ ] `python -m compileall`/engine smoke test passes on the built bundle.
- [ ] `EDUANCHOR_SMOKE=1` packaged-app smoke test passes.
- [ ] Version bumped in `code/desktop/package.json` and `code/engine/pyproject.toml`.
- [ ] Installer and portable build both produced.
- [ ] Optional: code-signed with a valid certificate.
- [ ] SHA-256 checksums published with the release.

## 11. Known limitations

- Windows is the primary target; macOS/Linux need packaging and path adjustments.
- No OCR, figures, formulas, or tables.
- The default bundle uses the hash embedder; BGE-M3 requires an opt-in build.
- Qwen3-8B is not bundled; the app expects a local OpenAI-compatible endpoint.
- The evaluation main table is a placeholder until the full Qwen run is complete.
