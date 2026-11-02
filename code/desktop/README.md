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

## Production build

```powershell
npm run build          # vite renderer + tsc electron main
npm run typecheck
npm run dist           # code-only electron-builder (expects ../engine/dist/eduanchor-engine)
npm run dist:full      # ZIP with engine + Qwen3-8B weights + llama.cpp runtime
```

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
