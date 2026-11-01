<script setup lang="ts">
import { computed, ref } from 'vue'
import type { KnowledgeCard } from '../types'

const props = defineProps<{ cards: KnowledgeCard[]; busy: boolean }>()

const kindLabels: Record<KnowledgeCard['kind'], string> = {
  definition: '定义',
  principle: '原理',
  procedure: '流程',
  example: '示例',
  concept: '概念'
}

const keyword = ref('')
const selected = ref<KnowledgeCard | null>(null)

const filtered = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return props.cards
  return props.cards.filter((card) =>
    [card.title, card.summary, ...card.key_points, ...card.tags]
      .join(' ')
      .toLowerCase()
      .includes(query)
  )
})
</script>

<template>
  <div class="pane">
    <div class="pane-toolbar">
      <div>
        <h2>知识点卡片库</h2>
        <p class="muted">每张卡片都锚定到教材页码与原文片段，可点击查看出处。</p>
      </div>
      <input v-model="keyword" class="search" placeholder="检索知识点 / 标签…" />
    </div>

    <div v-if="busy" class="loading">正在解析教材并生成卡片…</div>
    <div v-else-if="!filtered.length" class="empty-state">
      <h2>暂无卡片</h2>
      <p>导入教材后会自动生成结构化知识点卡片。</p>
    </div>

    <div v-else class="card-grid">
      <article
        v-for="card in filtered"
        :key="card.id"
        class="knowledge-card"
        @click="selected = card"
      >
        <div class="card-head">
          <span class="kind" :class="card.kind">{{ kindLabels[card.kind] }}</span>
          <span class="page">P{{ card.source.page }}</span>
        </div>
        <h3>{{ card.title }}</h3>
        <p class="summary">{{ card.summary }}</p>
        <ul v-if="card.key_points.length" class="key-points">
          <li v-for="point in card.key_points.slice(0, 3)" :key="point">{{ point }}</li>
        </ul>
        <div class="tags">
          <span v-for="tag in card.tags.slice(0, 4)" :key="tag">{{ tag }}</span>
        </div>
        <blockquote>{{ card.source.quote }}</blockquote>
      </article>
    </div>

    <div v-if="selected" class="modal-backdrop" @click.self="selected = null">
      <div class="modal">
        <div class="modal-head">
          <div>
            <span class="kind" :class="selected.kind">{{ kindLabels[selected.kind] }}</span>
            <h2>{{ selected.title }}</h2>
          </div>
          <button class="ghost" @click="selected = null">关闭</button>
        </div>
        <p>{{ selected.summary }}</p>
        <h4>关键表述</h4>
        <ul class="key-points">
          <li v-for="point in selected.key_points" :key="point">{{ point }}</li>
        </ul>
        <h4>教材原文 · 第 {{ selected.source.page }} 页</h4>
        <blockquote>{{ selected.source.quote }}</blockquote>
        <p class="muted" v-if="selected.source.bbox">
          定位框：{{ selected.source.bbox.join(', ') }}
        </p>
      </div>
    </div>
  </div>
</template>
