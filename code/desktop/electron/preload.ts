import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('eduanchor', {
  call: (method: string, params: Record<string, unknown> = {}) =>
    ipcRenderer.invoke('engine:call', method, params),
  pickTextbook: () => ipcRenderer.invoke('dialog:pickTextbook') as Promise<string[]>,
  openExternal: (url: string) => ipcRenderer.invoke('app:openExternal', url) as Promise<boolean>,
  info: () => ipcRenderer.invoke('app:info'),
  modelStatus: () => ipcRenderer.invoke('model:status'),
  downloadModel: () => ipcRenderer.invoke('model:download'),
  chooseModelDirectory: () => ipcRenderer.invoke('model:chooseDirectory'),
  openModelFolder: () => ipcRenderer.invoke('model:openFolder'),
  onModelStatus: (callback: (status: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: unknown): void => callback(status)
    ipcRenderer.on('model:status', listener)
    return () => ipcRenderer.removeListener('model:status', listener)
  }
})
