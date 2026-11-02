import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { spawn, type ChildProcess, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createHash } from 'node:crypto'
import { once } from 'node:events'
import {
  createReadStream,
  createWriteStream,
  existsSync,
  readFileSync,
  statSync,
  writeFileSync
} from 'node:fs'
import { copyFile, mkdir, rename, rm } from 'node:fs/promises'
import path from 'node:path'
import readline from 'node:readline'

type Pending = {
  resolve: (value: unknown) => void
  reject: (reason: Error) => void
}

class EngineClient {
  private child: ChildProcessWithoutNullStreams | null = null
  private pending = new Map<number, Pending>()
  private nextId = 1
  private ready: Promise<void> | null = null

  private engineDir(): string {
    return app.isPackaged
      ? path.join(process.resourcesPath, 'engine')
      : path.resolve(app.getAppPath(), '..', 'engine')
  }

  private spawnEngine(): ChildProcessWithoutNullStreams {
    const dir = this.engineDir()
    const packagedBin = path.join(dir, 'eduanchor-engine.exe')
    if (app.isPackaged && existsSync(packagedBin)) {
      return spawn(packagedBin, [], { cwd: dir, windowsHide: true })
    }
    if (existsSync(path.join(dir, '.venv', 'Scripts', 'eduanchor-rpc.exe'))) {
      return spawn(path.join(dir, '.venv', 'Scripts', 'eduanchor-rpc.exe'), [], {
        cwd: dir,
        windowsHide: true
      })
    }
    return spawn('uv', ['run', 'eduanchor-rpc'], {
      cwd: dir,
      shell: process.platform === 'win32',
      windowsHide: true,
      env: { ...process.env }
    })
  }

  private start(): Promise<void> {
    if (this.ready) return this.ready
    this.ready = new Promise((resolve, reject) => {
      let settled = false
      try {
        const child = this.spawnEngine()
        this.child = child
        const lines = readline.createInterface({ input: child.stdout })
        lines.on('line', (line) => this.handleLine(line))
        child.stderr.on('data', (chunk: Buffer) => {
          console.error('[engine]', chunk.toString('utf-8'))
        })
        child.on('error', (error) => {
          if (this.child !== child) return
          if (!settled) {
            settled = true
            reject(error)
          }
          this.failAll(error)
        })
        child.on('exit', (code) => {
          if (this.child !== child) return
          this.child = null
          this.ready = null
          const error = new Error(`engine exited with code ${code}`)
          if (!settled) {
            settled = true
            reject(error)
          }
          this.failAll(error)
        })
        const timer = setTimeout(() => {
          if (!settled) {
            settled = true
            reject(new Error('engine start timeout'))
          }
        }, 12000)
        child.once('spawn', () => {
          clearTimeout(timer)
          this.request('system.ping')
            .then(() => {
              settled = true
              resolve()
            })
            .catch((error) => {
              settled = true
              reject(error)
            })
        })
      } catch (error) {
        settled = true
        reject(error)
      }
    })
    return this.ready
  }

  private handleLine(line: string): void {
    const text = line.trim()
    if (!text) return
    let message: { id?: number; result?: unknown; error?: { message?: string } }
    try {
      message = JSON.parse(text)
    } catch {
      console.error('[engine] non-JSON output', text)
      return
    }
    if (typeof message.id !== 'number') return
    const waiter = this.pending.get(message.id)
    if (!waiter) return
    this.pending.delete(message.id)
    if (message.error) {
      waiter.reject(new Error(message.error.message ?? 'engine error'))
    } else {
      waiter.resolve(message.result)
    }
  }

  private failAll(error: Error): void {
    for (const waiter of this.pending.values()) waiter.reject(error)
    this.pending.clear()
  }

  private request<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const child = this.child
    if (!child) return Promise.reject(new Error('engine is not running'))
    const id = this.nextId++
    const payload = JSON.stringify({ jsonrpc: '2.0', id, method, params })
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject })
      child.stdin.write(payload + '\n', (error) => {
        if (error) {
          this.pending.delete(id)
          reject(error)
        }
      })
    })
  }

  async call<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    await this.start()
    return this.request<T>(method, params)
  }

  restart(): void {
    const child = this.child
    this.child = null
    this.ready = null
    this.failAll(new Error('engine restarting'))
    if (child && !child.killed) child.kill()
  }
}

const engine = new EngineClient()
let win: BrowserWindow | null = null
let modelServer: ChildProcess | null = null
let modelStart: Promise<void> | null = null

const MODEL_FILE = 'Qwen3-8B-Q4_K_M.gguf'
const MODEL_SUBDIR = 'Qwen3-8B-GGUF'
const MODEL_SIZE = 5_027_783_488
const MODEL_SHA256 = 'd98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785'
const MODEL_URLS = (
  process.env.EDUANCHOR_MODEL_URLS ||
  [
    'https://hf-mirror.com/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf',
    'https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf'
  ].join(',')
)
  .split(',')
  .map((url) => url.trim())
  .filter(Boolean)

type ModelState =
  | 'checking'
  | 'external'
  | 'missing'
  | 'downloading'
  | 'verifying'
  | 'starting'
  | 'ready'
  | 'error'

type ModelStatus = {
  state: ModelState
  provider: string
  installed: boolean
  modelPath: string
  directory: string
  source: string
  totalBytes: number
  downloadedBytes: number
  percent: number
  bytesPerSecond: number
  error: string
}

let modelStatus: ModelStatus = {
  state: 'checking',
  provider: 'llamacpp',
  installed: false,
  modelPath: '',
  directory: '',
  source: '',
  totalBytes: MODEL_SIZE,
  downloadedBytes: 0,
  percent: 0,
  bytesPerSecond: 0,
  error: ''
}
let modelDownloadTask: Promise<void> | null = null
let modelDownloadAbort: AbortController | null = null
let modelDownloadGeneration = 0

type DesktopSettings = {
  modelDir?: string
}

function repoRoot(): string {
  return app.isPackaged ? process.resourcesPath : path.resolve(app.getAppPath(), '..', '..')
}

function desktopSettingsPath(): string {
  return path.join(app.getPath('userData'), 'desktop-settings.json')
}

function readDesktopSettings(): DesktopSettings {
  try {
    return JSON.parse(readFileSync(desktopSettingsPath(), 'utf-8')) as DesktopSettings
  } catch {
    return {}
  }
}

function writeDesktopSettings(settings: DesktopSettings): void {
  writeFileSync(desktopSettingsPath(), `${JSON.stringify(settings, null, 2)}\n`, 'utf-8')
}

function modelFileFor(baseDir: string): string {
  return path.join(baseDir, MODEL_SUBDIR, MODEL_FILE)
}

function defaultModelBaseDir(): string {
  const local = process.env.LOCALAPPDATA || app.getPath('userData')
  return path.join(local, 'EduAnchor', 'models')
}

function configuredModelBaseDir(): string {
  if (process.env.EDUANCHOR_MODEL_DIR) return path.resolve(process.env.EDUANCHOR_MODEL_DIR)
  const saved = readDesktopSettings().modelDir
  if (saved) return path.resolve(saved)
  if (app.isPackaged) {
    const bundled = path.join(process.resourcesPath, 'models')
    if (existsSync(modelFileFor(bundled))) return bundled
    return defaultModelBaseDir()
  }
  return path.join(repoRoot(), 'models')
}

function currentModelFile(): string {
  return modelFileFor(configuredModelBaseDir())
}

function isCompleteModel(file: string): boolean {
  try {
    return statSync(file).size === MODEL_SIZE
  } catch {
    return false
  }
}

function partialFile(): string {
  return `${currentModelFile()}.part`
}

function partSize(): number {
  try {
    return statSync(partialFile()).size
  } catch {
    return 0
  }
}

function configuredProvider(): string {
  if (process.env.EDUANCHOR_LLM_PROVIDER) return process.env.EDUANCHOR_LLM_PROVIDER
  const dataDir = process.env.EDUANCHOR_DATA_DIR || path.join(process.env.LOCALAPPDATA || '', 'EduAnchor')
  try {
    const payload = JSON.parse(readFileSync(path.join(dataDir, 'model.json'), 'utf-8')) as {
      provider?: string
    }
    return payload.provider || 'llamacpp'
  } catch {
    return 'llamacpp'
  }
}

function publishModelStatus(patch: Partial<ModelStatus>): ModelStatus {
  modelStatus = {
    ...modelStatus,
    ...patch,
    provider: configuredProvider()
  }
  if (win && !win.isDestroyed()) {
    win.webContents.send('model:status', modelStatus)
  }
  return modelStatus
}

function refreshModelStatus(): ModelStatus {
  const file = currentModelFile()
  const installed = isCompleteModel(file)
  return publishModelStatus({
    state: configuredProvider() === 'llamacpp' ? 'checking' : 'external',
    installed,
    modelPath: file,
    directory: path.dirname(file),
    totalBytes: MODEL_SIZE,
    downloadedBytes: installed ? MODEL_SIZE : partSize(),
    percent: installed ? 100 : 0,
    bytesPerSecond: 0,
    error: ''
  })
}

function llamaServerFile(): string {
  const dir = app.isPackaged
    ? path.join(process.resourcesPath, 'llama')
    : path.join(repoRoot(), 'runtime', 'llama')
  return path.join(dir, 'llama-server.exe')
}

async function modelHealthy(port: number): Promise<boolean> {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`, {
      signal: AbortSignal.timeout(1500)
    })
    return response.ok
  } catch {
    return false
  }
}

async function startBundledModel(): Promise<void> {
  if (process.env.EDUANCHOR_DISABLE_BUNDLED === '1') {
    publishModelStatus({ state: 'external' })
    return
  }
  if (configuredProvider() !== 'llamacpp') {
    publishModelStatus({ state: 'external' })
    return
  }
  const model = currentModelFile()
  const server = llamaServerFile()
  if (!isCompleteModel(model)) {
    publishModelStatus({
      state: 'missing',
      installed: false,
      modelPath: model,
      directory: path.dirname(model),
      downloadedBytes: partSize(),
      percent: 0,
      error: ''
    })
    return
  }
  if (!existsSync(server)) {
    publishModelStatus({
      state: 'error',
      installed: true,
      error: `缺少 llama-server：${server}`
    })
    console.error('[model] llama-server not found:', server)
    return
  }
  if (await modelHealthy(8081)) {
    publishModelStatus({ state: 'ready', installed: true, error: '', percent: 100 })
    return
  }
  publishModelStatus({
    state: 'starting',
    installed: true,
    modelPath: model,
    directory: path.dirname(model),
    downloadedBytes: MODEL_SIZE,
    percent: 100,
    error: ''
  })
  modelServer = spawn(
    server,
    [
      '-m', model,
      '--alias', 'qwen3-8b',
      '--host', '127.0.0.1',
      '--port', '8081',
      '-c', '8192',
      '-ngl', '99',
      '--jinja',
      '--reasoning', 'off',
      '--no-webui'
    ],
    {
      cwd: path.dirname(server),
      windowsHide: true,
      stdio: ['ignore', 'ignore', 'pipe']
    }
  )
  modelServer.stderr?.on('data', (chunk: Buffer) => console.error('[model]', chunk.toString('utf-8')))
  modelServer.on('exit', () => {
    modelServer = null
  })
  const deadline = Date.now() + 180000
  while (Date.now() < deadline) {
    if (await modelHealthy(8081)) {
      console.log('[model] Qwen3-8B ready on 127.0.0.1:8081')
      publishModelStatus({ state: 'ready', installed: true, error: '', percent: 100 })
      return
    }
    if (!modelServer) break
    await new Promise((resolve) => setTimeout(resolve, 750))
  }
  publishModelStatus({
    state: 'error',
    installed: true,
    error: 'llama-server 启动超时；请检查显卡驱动或改用外部模型服务'
  })
  console.warn('[model] model health check timed out; engine will fall back')
}

async function ensureBundledModel(): Promise<void> {
  if (!modelStart) {
    modelStart = startBundledModel().finally(() => {
      modelStart = null
    })
  }
  return modelStart
}

function stopBundledModel(): void {
  modelStart = null
  if (!modelServer) return
  modelServer.kill()
  modelServer = null
}

async function sha256File(file: string): Promise<string> {
  const hash = createHash('sha256')
  for await (const chunk of createReadStream(file)) hash.update(chunk)
  return hash.digest('hex')
}

function publishDownload(generation: number, patch: Partial<ModelStatus>): void {
  if (generation !== modelDownloadGeneration) return
  publishModelStatus(patch)
}

async function downloadToPart(
  url: string,
  part: string,
  signal: AbortSignal,
  generation: number
): Promise<void> {
  let start = partSize()
  if (start >= MODEL_SIZE) {
    await rm(part, { force: true })
    start = 0
  }
  const headers: Record<string, string> = start > 0 ? { Range: `bytes=${start}-` } : {}
  const response = await fetch(url, { headers, redirect: 'follow', signal })
  if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`)
  if (!response.body) throw new Error('下载响应为空')
  const resumed = start > 0 && response.status === 206
  const writer = createWriteStream(part, { flags: resumed ? 'a' : 'w' })
  let downloaded = resumed ? start : 0
  const startedAt = Date.now()
  let lastReport = 0
  try {
    const reader = response.body.getReader()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (signal.aborted) throw new Error('下载已取消')
      const buffer = Buffer.from(value)
      downloaded += buffer.byteLength
      if (!writer.write(buffer)) await once(writer, 'drain')
      const now = Date.now()
      if (now - lastReport > 300) {
        lastReport = now
        const elapsed = Math.max((now - startedAt) / 1000, 0.1)
        publishDownload(generation, {
          state: 'downloading',
          source: url,
          downloadedBytes: downloaded,
          percent: Math.min(100, (downloaded / MODEL_SIZE) * 100),
          bytesPerSecond: Math.round((downloaded - start) / elapsed),
          error: ''
        })
      }
    }
    await new Promise<void>((resolve, reject) => {
      writer.once('error', reject)
      writer.end(resolve)
    })
  } catch (error) {
    writer.destroy()
    throw error
  }
}

async function runModelDownload(generation: number, signal: AbortSignal): Promise<void> {
  const file = currentModelFile()
  const part = `${file}.part`
  if (isCompleteModel(file)) {
    await ensureBundledModel()
    return
  }
  await mkdir(path.dirname(file), { recursive: true })
  let lastError: unknown = null
  for (const url of MODEL_URLS) {
    if (signal.aborted || generation !== modelDownloadGeneration) return
    try {
      publishDownload(generation, {
        state: 'downloading',
        source: url,
        downloadedBytes: partSize(),
        percent: Math.min(100, (partSize() / MODEL_SIZE) * 100),
        bytesPerSecond: 0,
        error: ''
      })
      await downloadToPart(url, part, signal, generation)
      lastError = null
      break
    } catch (error) {
      if (signal.aborted || generation !== modelDownloadGeneration) return
      lastError = error
      console.warn('[model] download source failed:', url, error)
    }
  }
  if (signal.aborted || generation !== modelDownloadGeneration) return
  if (lastError || !existsSync(part)) {
    throw lastError instanceof Error ? lastError : new Error('模型下载失败')
  }
  publishDownload(generation, {
    state: 'verifying',
    downloadedBytes: MODEL_SIZE,
    percent: 100,
    bytesPerSecond: 0,
    error: ''
  })
  const digest = await sha256File(part)
  if (digest.toLowerCase() !== MODEL_SHA256) {
    await rm(part, { force: true })
    throw new Error('模型校验失败，请重试下载')
  }
  await rm(file, { force: true })
  await rename(part, file)
  if (generation !== modelDownloadGeneration) return
  publishDownload(generation, {
    state: 'starting',
    installed: true,
    modelPath: file,
    directory: path.dirname(file),
    downloadedBytes: MODEL_SIZE,
    percent: 100,
    bytesPerSecond: 0,
    error: ''
  })
  await ensureBundledModel()
  engine.restart()
}

function triggerModelDownload(): ModelStatus {
  if (configuredProvider() !== 'llamacpp') {
    return publishModelStatus({ state: 'external' })
  }
  if (process.env.EDUANCHOR_DISABLE_MODEL_DOWNLOAD === '1') {
    return publishModelStatus({ state: 'missing' })
  }
  if (isCompleteModel(currentModelFile())) {
    void ensureBundledModel()
    return modelStatus
  }
  if (modelDownloadTask) return modelStatus
  const generation = ++modelDownloadGeneration
  const controller = new AbortController()
  modelDownloadAbort = controller
  const downloaded = partSize()
  publishModelStatus({
    state: downloaded > 0 ? 'downloading' : 'missing',
    installed: false,
    modelPath: currentModelFile(),
    directory: path.dirname(currentModelFile()),
    downloadedBytes: downloaded,
    percent: Math.min(100, (downloaded / MODEL_SIZE) * 100),
    bytesPerSecond: 0,
    error: ''
  })
  modelDownloadTask = runModelDownload(generation, controller.signal)
    .catch((error) => {
      if (generation !== modelDownloadGeneration) return
      publishModelStatus({
        state: 'error',
        installed: isCompleteModel(currentModelFile()),
        downloadedBytes: partSize(),
        bytesPerSecond: 0,
        error: error instanceof Error ? error.message : String(error)
      })
    })
    .finally(() => {
      if (generation !== modelDownloadGeneration) return
      modelDownloadTask = null
      modelDownloadAbort = null
    })
  return modelStatus
}

async function cancelModelDownload(): Promise<void> {
  modelDownloadGeneration += 1
  modelDownloadAbort?.abort()
  modelDownloadAbort = null
  const task = modelDownloadTask
  modelDownloadTask = null
  if (task) await task.catch(() => undefined)
}

async function initializeModel(): Promise<void> {
  refreshModelStatus()
  if (configuredProvider() !== 'llamacpp') {
    publishModelStatus({ state: 'external', error: '' })
    return
  }
  if (isCompleteModel(currentModelFile())) {
    await ensureBundledModel()
    return
  }
  if (process.env.EDUANCHOR_DISABLE_MODEL_DOWNLOAD === '1') {
    publishModelStatus({ state: 'missing', installed: false, error: '' })
    return
  }
  triggerModelDownload()
  if (process.env.EDUANCHOR_SMOKE === '1' && modelDownloadTask) {
    await modelDownloadTask
  }
}

async function moveFile(source: string, target: string): Promise<void> {
  try {
    await rename(source, target)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EXDEV') throw error
    await copyFile(source, target)
    await rm(source, { force: true })
  }
}

async function setModelDirectory(baseDir: string): Promise<ModelStatus> {
  const targetBase = path.resolve(baseDir)
  const previousBase = configuredModelBaseDir()
  if (targetBase === path.resolve(previousBase)) return modelStatus
  const previousFile = currentModelFile()
  const previousPart = `${previousFile}.part`
  const hadModel = isCompleteModel(previousFile)
  const hadPart = existsSync(previousPart)
  await cancelModelDownload()
  stopBundledModel()
  const targetFile = modelFileFor(targetBase)
  const targetPart = `${targetFile}.part`
  try {
    await mkdir(path.dirname(targetFile), { recursive: true })
    if (hadModel && !isCompleteModel(targetFile)) {
      await moveFile(previousFile, targetFile)
    }
    if (hadPart && !existsSync(targetPart)) {
      await moveFile(previousPart, targetPart)
    }
    writeDesktopSettings({ modelDir: targetBase })
  } catch (error) {
    writeDesktopSettings({ modelDir: previousBase })
    publishModelStatus({
      state: 'error',
      error: error instanceof Error ? error.message : String(error)
    })
    throw error
  }
  const installed = isCompleteModel(targetFile)
  publishModelStatus({
    state: installed ? 'checking' : 'missing',
    installed,
    modelPath: targetFile,
    directory: path.dirname(targetFile),
    downloadedBytes: installed ? MODEL_SIZE : partSize(),
    percent: installed ? 100 : 0,
    bytesPerSecond: 0,
    error: ''
  })
  if (installed) {
    await ensureBundledModel()
    engine.restart()
  } else if (configuredProvider() === 'llamacpp') {
    triggerModelDownload()
  }
  return modelStatus
}

async function chooseModelDirectory(): Promise<ModelStatus | null> {
  if (!win) return null
  const result = await dialog.showOpenDialog(win, {
    title: '选择模型存储位置',
    defaultPath: configuredModelBaseDir(),
    properties: ['openDirectory', 'createDirectory']
  })
  if (result.canceled || !result.filePaths[0]) return null
  return setModelDirectory(result.filePaths[0])
}

function createWindow(): void {
  win = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1040,
    minHeight: 700,
    backgroundColor: '#f5f7f6',
    title: 'EduAnchor · 教材锚定解读',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })
  const devUrl = process.env.VITE_DEV_SERVER_URL
  if (devUrl) {
    void win.loadURL(devUrl)
  } else {
    void win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
  win.on('closed', () => {
    win = null
  })
}

app.whenReady().then(async () => {
  createWindow()
  const modelInit = initializeModel()
  void modelInit

  if (process.env.EDUANCHOR_SMOKE === '1') {
    void (async () => {
      try {
        await modelInit
        const status = await engine.call<Record<string, unknown>>('system.status')
        console.log('SMOKE_STATUS', JSON.stringify(status))
        const model = await engine.call<{ config: { provider: string; model: string } }>(
          'settings.getModel'
        )
        console.log('SMOKE_MODEL', model.config.provider, model.config.model)
        const doc = await engine.call<{ id: string }>('library.seedSample')
        const answer = await engine.call<{ refused: boolean; support_rate: number }>('qa.ask', {
          docId: doc.id,
          question: '什么是机器学习？'
        })
        console.log('SMOKE_QA', answer.refused, answer.support_rate)
        console.log('SMOKE_OK')
        app.quit()
      } catch (error) {
        console.error('SMOKE_FAIL', error)
        app.exit(1)
      }
    })()
  }

  ipcMain.handle('engine:call', async (_event, method: string, params: Record<string, unknown>) => {
    return engine.call(method, params)
  })

  ipcMain.handle('model:status', () => modelStatus)
  ipcMain.handle('model:download', () => triggerModelDownload())
  ipcMain.handle('model:chooseDirectory', () => chooseModelDirectory())
  ipcMain.handle('model:openFolder', async () => {
    const directory = path.dirname(currentModelFile())
    await mkdir(directory, { recursive: true })
    await shell.openPath(directory)
    return directory
  })

  ipcMain.handle('dialog:pickTextbook', async () => {
    if (!win) return []
    const result = await dialog.showOpenDialog(win, {
      title: '选择教材文件',
      properties: ['openFile'],
      filters: [
        { name: '教材', extensions: ['pdf', 'md', 'markdown', 'txt'] },
        { name: '所有文件', extensions: ['*'] }
      ]
    })
    return result.canceled ? [] : result.filePaths
  })

  ipcMain.handle('app:openExternal', async (_event, url: string) => {
    if (!/^https?:\/\//i.test(url)) return false
    await shell.openExternal(url)
    return true
  })

  ipcMain.handle('app:info', () => ({
    version: app.getVersion(),
    electron: process.versions.electron,
    platform: process.platform,
    packaged: app.isPackaged
  }))

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopBundledModel()
})
