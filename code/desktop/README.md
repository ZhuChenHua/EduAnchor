# EduAnchor Desktop

Electron 33 + Vue 3 + TypeScript client.

## Development

```powershell
npm install
npm run dev
```

`npm run dev` starts Vite and Electron. Electron spawns the Python engine from
`../engine`; if `.venv\Scripts\eduanchor-rpc.exe` exists it is used directly,
otherwise `uv run eduanchor-rpc`. When `../../models/Qwen3-8B-GGUF` and
`../../runtime/llama` exist, Electron also starts the built-in Qwen3-8B
llama.cpp server on `127.0.0.1:8081`.

The packaged app includes the engine and llama.cpp runtime. On first launch it
downloads `Qwen3-8B-Q4_K_M.gguf` (about 5.0 GB), verifies its SHA-256, and starts
the local server. The default model directory is
`%LOCALAPPDATA%\EduAnchor\models\Qwen3-8B-GGUF`; users can change it in
**Model settings → Built-in model storage**. Set `EDUANCHOR_MODEL_DIR` to
override the directory, or `EDUANCHOR_DISABLE_MODEL_DOWNLOAD=1` to use an
external provider without downloading.

## Production build

```powershell
npm run build          # vite renderer + tsc electron main
npm run typecheck
npm run dist           # NSIS installer + portable exe (expects ../engine/dist/eduanchor-engine)
```

The installer contains the PyInstaller engine under `resources/engine` and the
llama.cpp runtime under `resources/llama`; model weights are not bundled.

The renderer is loaded with `nodeIntegration: false` and `contextIsolation: true`.
All engine access goes through the preload bridge and IPC.

## UI

- **Library**: import PDF/Markdown/TXT, load the bundled sample, delete books.
- **Knowledge cards**: searchable cards with type, tags, page, quote, bbox.
- **Model settings**: use the built-in Qwen3-8B (default), Ollama, vLLM, or a
  remote OpenAI-compatible endpoint; test the connection and store the key
  locally.
- **Grounded QA**: explain/socratic modes, C1–C7 condition switch, citations,
  support/coverage metrics, full agent trace.
- **Evaluation**: run the C1–C7 ablation and inspect the resulting table.
