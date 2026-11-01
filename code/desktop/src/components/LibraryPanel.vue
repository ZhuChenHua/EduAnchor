<script setup lang="ts">
import type { DocumentInfo, EngineStatus } from '../types'

defineProps<{
  documents: DocumentInfo[]
  activeId: string
  busy: boolean
  status: EngineStatus | null
}>()

defineEmits<{
  (event: 'select', id: string): void
  (event: 'import'): void
  (event: 'seed'): void
  (event: 'remove', id: string): void
  (event: 'settings'): void
}>()
</script>

<template>
  <aside class="library">
    <div class="brand">
      <div class="brand-mark">EA</div>
      <div>
        <strong>EduAnchor</strong>
        <span>教材锚定 · 离线桌面端</span>
      </div>
    </div>

    <div class="library-actions">
      <button class="primary" :disabled="busy" @click="$emit('import')">
        {{ busy ? '处理中…' : '导入教材' }}
      </button>
      <button class="ghost" :disabled="busy" @click="$emit('seed')">载入示例教材</button>
    </div>

    <p class="section-title">教材库</p>
    <ul class="doc-list">
      <li v-for="doc in documents" :key="doc.id">
        <button
          class="doc-item"
          :class="{ active: doc.id === activeId }"
          @click="$emit('select', doc.id)"
        >
          <span class="doc-title">{{ doc.title }}</span>
          <span class="doc-meta">{{ doc.pages }} 页 · {{ doc.card_count }} 卡片</span>
        </button>
        <button class="doc-remove" title="删除" @click.stop="$emit('remove', doc.id)">×</button>
      </li>
      <li v-if="!documents.length" class="doc-empty">暂无教材</li>
    </ul>

    <div class="runtime-card">
      <p class="section-title">运行状态</p>
      <div class="runtime-row">
        <span>生成模型</span>
        <span class="pill" :class="status?.llm.available ? 'ok' : 'warn'">
          {{ status?.llm.available ? status.llm.name : '抽取式降级' }}
        </span>
      </div>
      <div class="runtime-row">
        <span>提供方</span>
        <span class="muted">{{ status?.llm.provider ?? '—' }} · {{ status?.llm.is_local ? '本地' : '远程 API' }}</span>
      </div>
      <div class="runtime-row">
        <span>向量后端</span>
        <span class="pill">{{ status?.embedder.name ?? '—' }}</span>
      </div>
      <div class="runtime-row">
        <span>知识库</span>
        <span class="muted">
          {{ status?.counts.chunks ?? 0 }} 段 / {{ status?.counts.cards ?? 0 }} 卡片
        </span>
      </div>
      <button class="ghost settings-button" @click="$emit('settings')">模型设置</button>
      <p class="hint">
        默认连接本地 Ollama <code>qwen3:8b</code>；也可切换到 OpenAI、DeepSeek、DashScope 等兼容 API。
      </p>
    </div>
  </aside>
</template>
