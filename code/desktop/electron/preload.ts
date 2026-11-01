import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('eduanchor', {
  call: (method: string, params: Record<string, unknown> = {}) =>
    ipcRenderer.invoke('engine:call', method, params),
  pickTextbook: () => ipcRenderer.invoke('dialog:pickTextbook') as Promise<string[]>,
  openExternal: (url: string) => ipcRenderer.invoke('app:openExternal', url) as Promise<boolean>,
  info: () => ipcRenderer.invoke('app:info')
})
