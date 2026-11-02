<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import LibraryPanel from './components/LibraryPanel.vue'
import CardGrid from './components/CardGrid.vue'
import AskPanel from './components/AskPanel.vue'
import EvalPanel from './components/EvalPanel.vue'
import ModelSettings from './components/ModelSettings.vue'
import type { DocumentInfo, EngineStatus, KnowledgeCard, ModelStatus } from './types'

const documents = ref<DocumentInfo[]>([])
const activeId = ref('')
const cards = ref<KnowledgeCard[]>([])
const status = ref<EngineStatus | null>(null)
const tab = ref<'cards' | 'qa' | 'eval'>('cards')
const busy = ref(false)
const error = ref('')
const showSettings = ref(false)
const modelStatus = ref<ModelStatus | null>(null)
let unsubscribeModelStatus: (() => void) | null = null

const activeDoc = computed(() => documents.value.find((doc) => doc.id === activeId.value) ?? null)
const modelNeedsAttention = computed(() => {
  const state = modelStatus.value?.state
  return state === 'checking' || state === 'missing' || state === 'downloading' ||
    state === 'verifying' || state === 'starting' || state === 'error'
})
const modelBannerText = computed(() => {
  const status = modelStatus.value
  if (!status) return ''
  if (status.state === 'downloading') {
    return `正在下载内置模型 ${status.percent.toFixed(1)}% · ${formatBytes(status.downloadedBytes)} / ${formatBytes(status.totalBytes)}`
  }
  if (status.state === 'verifying') return '正在校验内置模型完整性…'
  if (status.state === 'starting') return '内置模型已就绪，正在启动本地推理服务…'
  if (status.state === 'error') return status.error || '内置模型准备失败，可在模型设置中重试。'
  if (status.state === 'checking') return '正在检查内置模型…'
  return '首次使用需要下载约 5.0 GB 的 Qwen3-8B 模型，下载后即可完全离线运行。'
})

function formatBytes(value: number): string {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index > 2 ? 2 : 1)} ${units[index]}`
}

async function call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  return window.eduanchor.call<T>(method, params)
}

async function refreshDocs(): Promise<void> {
  documents.value = await call<DocumentInfo[]>('library.list')
}

async function refreshStatus(): Promise<void> {
  status.value = await call<EngineStatus>('system.status')
}

async function loadModelStatus(): Promise<void> {
  modelStatus.value = await window.eduanchor.modelStatus()
  if (modelStatus.value.state === 'missing' || modelStatus.value.state === 'downloading') {
    showSettings.value = true
  }
}

async function loadCards(): Promise<void> {
  if (!activeId.value) {
    cards.value = []
    return
  }
  cards.value = await call<KnowledgeCard[]>('cards.list', { docId: activeId.value })
}

async function selectDoc(id: string): Promise<void> {
  activeId.value = id
  tab.value = 'cards'
  await loadCards()
}

async function importTextbook(): Promise<void> {
  error.value = ''
  const paths = await window.eduanchor.pickTextbook()
  if (!paths.length) return
  busy.value = true
  try {
    const doc = await call<DocumentInfo>('library.importFile', { path: paths[0] })
    await refreshDocs()
    await selectDoc(doc.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function seedSample(): Promise<void> {
  error.value = ''
  busy.value = true
  try {
    const doc = await call<DocumentInfo>('library.seedSample')
    await refreshDocs()
    await selectDoc(doc.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function removeDoc(id: string): Promise<void> {
  if (!window.confirm('删除该教材及其卡片、索引与会话记录？')) return
  busy.value = true
  try {
    await call('library.delete', { docId: id })
    if (activeId.value === id) {
      activeId.value = ''
      cards.value = []
    }
    await refreshDocs()
    if (!activeId.value && documents.value.length) await selectDoc(documents.value[0].id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  unsubscribeModelStatus = window.eduanchor.onModelStatus((next) => {
    modelStatus.value = next
    if (next.state === 'ready') void refreshStatus()
  })
  try {
    await loadModelStatus()
    status.value = await call<EngineStatus>('system.status')
    await refreshDocs()
    if (documents.value.length) await selectDoc(documents.value[0].id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
})

onBeforeUnmount(() => {
  unsubscribeModelStatus?.()
})
</script>

<template>
  <div class="app-shell">
    <LibraryPanel
      :documents="documents"
      :active-id="activeId"
      :busy="busy"
      :status="status"
      @select="selectDoc"
      @import="importTextbook"
      @seed="seedSample"
      @remove="removeDoc"
      @settings="showSettings = true"
    />

    <main class="workspace">
      <header class="workspace-header">
        <div>
          <p class="eyebrow">TEXTBOOK-GROUNDED INTERPRETATION</p>
          <h1>{{ activeDoc ? activeDoc.title : '教材锚定多智能体解读' }}</h1>
          <p v-if="activeDoc" class="meta">
            {{ activeDoc.pages }} 页 · {{ activeDoc.chunk_count }} 个段落 · {{ activeDoc.card_count }} 张卡片 ·
            索引 {{ activeDoc.embed_backend }}
          </p>
          <p v-else class="meta">导入 PDF / Markdown 教材，或载入内置示例教材开始。</p>
        </div>
        <nav class="tabs">
          <button :class="{ active: tab === 'cards' }" @click="tab = 'cards'">知识点卡片</button>
          <button :class="{ active: tab === 'qa' }" :disabled="!activeDoc" @click="tab = 'qa'">
            锚定问答
          </button>
          <button :class="{ active: tab === 'eval' }" :disabled="!activeDoc" @click="tab = 'eval'">
            评测面板
          </button>
        </nav>
      </header>

      <section v-if="modelNeedsAttention" class="model-banner" :class="{ bad: modelStatus?.state === 'error' }">
        <div>
          <strong>内置模型正在准备</strong>
          <p>{{ modelBannerText }}</p>
        </div>
        <button class="ghost" @click="showSettings = true">查看进度 / 更改位置</button>
      </section>

      <p v-if="error" class="error-banner">{{ error }}</p>

      <section class="workspace-body">
        <CardGrid v-if="tab === 'cards'" :cards="cards" :busy="busy" />
        <AskPanel v-else-if="tab === 'qa' && activeDoc" :doc="activeDoc" :status="status" />
        <EvalPanel v-else-if="tab === 'eval' && activeDoc" :doc="activeDoc" />
        <div v-else class="empty-state">
          <h2>还没有可用的教材</h2>
          <p>点击左侧“载入示例教材”，或导入你自己的 PDF 教材。</p>
        </div>
      </section>
    </main>

    <ModelSettings
      v-if="showSettings"
      @close="showSettings = false"
      @saved="refreshStatus"
    />
  </div>
</template>
