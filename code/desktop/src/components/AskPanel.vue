<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Answer, Citation, DocumentInfo, EngineStatus } from '../types'

const props = defineProps<{ doc: DocumentInfo; status: EngineStatus | null }>()

const messages = ref<Answer[]>([])
const question = ref('')
const mode = ref<'explain' | 'socratic'>('explain')
const condition = ref('c7')
const loading = ref(false)
const error = ref('')
const openTrace = ref<number | null>(null)
const activeCitation = ref<Citation | null>(null)

const suggestions = [
  '什么是机器学习？',
  '监督学习和无监督学习有什么区别？',
  '什么是过拟合？如何缓解？',
  '教材锚定的含义是什么？'
]

watch(
  () => props.doc.id,
  () => {
    messages.value = []
    openTrace.value = null
  }
)

async function submit(text?: string): Promise<void> {
  const content = (text ?? question.value).trim()
  if (!content || loading.value) return
  loading.value = true
  error.value = ''
  question.value = ''
  try {
    const answer = await window.eduanchor.call<Answer>('qa.ask', {
      docId: props.doc.id,
      question: content,
      mode: mode.value,
      condition: condition.value
    })
    messages.value.push(answer)
    openTrace.value = null
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="pane qa-pane">
    <div class="pane-toolbar">
      <div>
        <h2>教材锚定问答</h2>
        <p class="muted">
          回答受教材片段约束；证据不足时会明确拒答，并给出最接近的教材位置。
        </p>
      </div>
      <div class="control-row">
        <div class="segmented">
          <button :class="{ active: mode === 'explain' }" @click="mode = 'explain'">解释</button>
          <button :class="{ active: mode === 'socratic' }" @click="mode = 'socratic'">苏格拉底</button>
        </div>
        <select v-model="condition" class="select" title="消融条件">
          <option value="c7">C7 源文贴近（最终）</option>
          <option value="c6">C6 验证优先</option>
          <option value="c5">C5 完整系统</option>
          <option value="c4">C4 多智能体</option>
          <option value="c3">C3 混合检索</option>
          <option value="c2">C2 向量 RAG</option>
          <option value="c1">C1 裸模型</option>
        </select>
      </div>
    </div>

    <div class="chat">
      <div v-if="!messages.length && !loading" class="chat-empty">
        <h2>{{ mode === 'socratic' ? '让教材带着你追问' : '从教材出发，而不是从模型记忆出发' }}</h2>
        <p>每个回答都会返回页码、原文引用与完整智能体轨迹。</p>
        <div class="suggestions">
          <button v-for="item in suggestions" :key="item" @click="submit(item)">{{ item }}</button>
        </div>
      </div>

      <div v-for="(message, index) in messages" :key="message.session_id ?? index" class="turn">
        <div class="bubble user">{{ message.question }}</div>
        <div class="bubble assistant" :class="{ refused: message.refused }">
          <div class="answer-head">
            <span class="badge" :class="message.refused ? 'danger' : 'success'">
              {{ message.refused ? '教材边界拒答' : '教材锚定回答' }}
            </span>
            <span class="badge">{{ message.condition.toUpperCase() }}</span>
            <span class="badge">{{ message.mode === 'socratic' ? '苏格拉底' : '解释' }}</span>
            <span class="muted small">
              支撑率 {{ (message.support_rate * 100).toFixed(0) }}% · 覆盖率
              {{ (message.coverage * 100).toFixed(0) }}% · {{ message.latency_ms.toFixed(0) }} ms
            </span>
          </div>

          <pre class="answer-text">{{ message.answer }}</pre>
          <p v-if="message.refused && message.reason" class="reason">拒答原因：{{ message.reason }}</p>

          <div v-if="message.citations.length" class="citations">
            <p class="section-title">引用与出处</p>
            <button
              v-for="(citation, citeIndex) in message.citations"
              :key="citation.chunk_id"
              class="citation-chip"
              @click="activeCitation = citation"
            >
              [{{ citeIndex + 1 }}] 第 {{ citation.page }} 页
              <span>{{ citation.quote.slice(0, 46) }}…</span>
            </button>
          </div>

          <button class="trace-toggle" @click="openTrace = openTrace === index ? null : index">
            {{ openTrace === index ? '收起智能体轨迹' : '查看智能体轨迹' }}
          </button>
          <ol v-if="openTrace === index" class="trace">
            <li v-for="step in message.trace" :key="step.agent + step.action">
              <span class="trace-agent">{{ step.agent }}</span>
              <span class="trace-action">{{ step.action }}</span>
              <span class="trace-detail">{{ step.detail }}</span>
              <span class="trace-time">{{ step.elapsed_ms.toFixed(0) }} ms</span>
            </li>
          </ol>
        </div>
      </div>

      <div v-if="loading" class="thinking">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        正在检索教材、生成并校验…
      </div>
      <p v-if="error" class="error-banner">{{ error }}</p>
    </div>

    <form class="composer" @submit.prevent="submit()">
      <textarea
        v-model="question"
        rows="2"
        placeholder="向这本教材提问，例如：为什么模型评估要使用独立的数据？"
        @keydown.enter.exact.prevent="submit()"
      ></textarea>
      <button class="primary" type="submit" :disabled="loading || !question.trim()">发送</button>
    </form>

    <div v-if="activeCitation" class="modal-backdrop" @click.self="activeCitation = null">
      <div class="modal">
        <div class="modal-head">
          <h2>第 {{ activeCitation.page }} 页 · 原文</h2>
          <button class="ghost" @click="activeCitation = null">关闭</button>
        </div>
        <blockquote>{{ activeCitation.quote }}</blockquote>
        <p class="muted">引用相关度：{{ activeCitation.score.toFixed(3) }}</p>
      </div>
    </div>
  </div>
</template>
