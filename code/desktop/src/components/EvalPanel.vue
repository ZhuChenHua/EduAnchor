<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DocumentInfo, EvalMetrics, EvalResponse } from '../types'

const props = defineProps<{ doc: DocumentInfo }>()

const running = ref(false)
const error = ref('')
const response = ref<EvalResponse | null>(null)

const conditionLabels: Record<string, string> = {
  c1: 'C1 裸模型',
  c2: 'C2 向量 RAG',
  c3: 'C3 混合检索+重排',
  c4: 'C4 多智能体',
  c5: 'C5 完整系统'
}

const rows = computed(() => {
  if (!response.value) return []
  return Object.entries(response.value.results)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([condition, payload]) => ({
      condition,
      label: conditionLabels[condition] ?? condition.toUpperCase(),
      metrics: payload.metrics
    }))
})

async function run(): Promise<void> {
  running.value = true
  error.value = ''
  try {
    response.value = await window.eduanchor.call<EvalResponse>('eval.run', {
      docId: props.doc.id,
      allConditions: true
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    running.value = false
  }
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}
</script>

<template>
  <div class="pane">
    <div class="pane-toolbar">
      <div>
        <h2>评测面板</h2>
        <p class="muted">
          在内置教材 QA 集上运行 C1–C5 消融：支撑率、幻觉率、误拒率与超纲拒答率。
        </p>
      </div>
      <button class="primary" :disabled="running" @click="run">
        {{ running ? '评测运行中…' : '运行消融评测' }}
      </button>
    </div>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <div v-if="!response && !running" class="empty-state">
      <h2>尚未运行评测</h2>
      <p>点击右上角按钮，引擎将依次运行 C1–C5 五种条件并汇总指标。</p>
    </div>

    <div v-if="running" class="loading">正在运行评测，请稍候…</div>

    <div v-if="response" class="eval-body">
      <p class="muted">样本数：{{ response.n }}（教材内 + 教材外）</p>
      <table class="eval-table">
        <thead>
          <tr>
            <th>条件</th>
            <th>支撑率 ↑</th>
            <th>幻觉率 ↓</th>
            <th>教材内误拒 ↓</th>
            <th>超纲拒答 ↑</th>
            <th>相关性 ↑</th>
            <th>延迟 (ms) ↓</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.condition">
            <td class="condition">{{ row.label }}</td>
            <td>{{ percent(row.metrics.support_rate) }}</td>
            <td>{{ percent(row.metrics.hallucination_rate) }}</td>
            <td>{{ percent(row.metrics.false_refusal_rate) }}</td>
            <td>{{ percent(row.metrics.refusal_accuracy) }}</td>
            <td>{{ percent(row.metrics.relevance) }}</td>
            <td>{{ row.metrics.mean_latency_ms.toFixed(0) }}</td>
          </tr>
        </tbody>
      </table>

      <div class="eval-cards">
        <div v-for="row in rows" :key="row.condition">
          <span class="eyebrow">{{ row.label }}</span>
          <strong>{{ percent(row.metrics.support_rate) }}</strong>
          <span class="muted">教材支撑率 · CI {{ percent(row.metrics.support_ci[0]) }}–{{ percent(row.metrics.support_ci[1]) }}</span>
        </div>
      </div>
      <p class="hint">
        以上为当前离线引擎的实测值。接入 Qwen3-8B 后重新运行即可生成论文表格（
        <code>uv run eduanchor eval --all-conditions --latex-dir ../../paper/tables</code>）。
      </p>
    </div>
  </div>
</template>
