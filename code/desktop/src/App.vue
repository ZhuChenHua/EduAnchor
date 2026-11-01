<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import LibraryPanel from './components/LibraryPanel.vue'
import CardGrid from './components/CardGrid.vue'
import AskPanel from './components/AskPanel.vue'
import EvalPanel from './components/EvalPanel.vue'
import ModelSettings from './components/ModelSettings.vue'
import type { DocumentInfo, EngineStatus, KnowledgeCard } from './types'

const documents = ref<DocumentInfo[]>([])
const activeId = ref('')
const cards = ref<KnowledgeCard[]>([])
const status = ref<EngineStatus | null>(null)
const tab = ref<'cards' | 'qa' | 'eval'>('cards')
const busy = ref(false)
const error = ref('')
const showSettings = ref(false)

const activeDoc = computed(() => documents.value.find((doc) => doc.id === activeId.value) ?? null)

async function call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  return window.eduanchor.call<T>(method, params)
}

async function refreshDocs(): Promise<void> {
  documents.value = await call<DocumentInfo[]>('library.list')
}

async function refreshStatus(): Promise<void> {
  status.value = await call<EngineStatus>('system.status')
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
  try {
    status.value = await call<EngineStatus>('system.status')
    await refreshDocs()
    if (documents.value.length) await selectDoc(documents.value[0].id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
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
