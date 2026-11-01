import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync } from 'node:fs'
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
          if (!settled) {
            settled = true
            reject(error)
          }
          this.failAll(error)
        })
        child.on('exit', (code) => {
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
}

const engine = new EngineClient()
let win: BrowserWindow | null = null

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

app.whenReady().then(() => {
  createWindow()

  if (process.env.EDUANCHOR_SMOKE === '1') {
    void (async () => {
      try {
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
