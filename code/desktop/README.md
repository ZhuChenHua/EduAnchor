# EduAnchor Desktop

Electron 33 + Vue 3 + TypeScript client.

## Development

```powershell
npm install
npm run dev
```

`npm run dev` starts Vite and Electron. Electron spawns the Python engine from
`../engine`; if `.venv\Scripts\eduanchor-rpc.exe` exists it is used directly,
otherwise `uv run eduanchor-rpc`.

## Production build

```powershell
npm run build          # vite renderer + tsc electron main
npm run typecheck
npm run dist           # electron-builder (expects ../engine/dist/eduanchor-engine)
```

The renderer is loaded with `nodeIntegration: false` and `contextIsolation: true`.
All engine access goes through the preload bridge and IPC.

## UI

- **Library**: import PDF/Markdown/TXT, load the bundled sample, delete books.
- **Knowledge cards**: searchable cards with type, tags, page, quote, bbox.
- **Model settings**: choose Ollama (local default), OpenAI, DeepSeek,
  DashScope, Moonshot, SiliconFlow, or a custom OpenAI-compatible endpoint;
  test the connection and store the key locally.
- **Grounded QA**: explain/socratic modes, C1–C5 condition switch, citations,
  support/coverage metrics, full agent trace.
- **Evaluation**: run the C1–C5 ablation and inspect the resulting table.
