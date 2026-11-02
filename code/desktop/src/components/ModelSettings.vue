<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type {
  ModelConfigPublic,
  ModelSettingsResponse,
  ModelStatus,
  ModelTestResult,
  ProviderInfo
} from '../types'

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'saved'): void
}>()

const providers = ref<Record<string, ProviderInfo>>({})
const provider = ref('llamacpp')
const baseUrl = ref('http://127.0.0.1:8081/v1')
const model = ref('qwen3-8b')
const apiKey = ref('')
const temperature = ref(0.2)
const maxTokens = ref(900)
const hasKey = ref(false)
const requiresKey = ref(false)
const isLocal = ref(true)
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<ModelTestResult | null>(null)
const error = ref('')
const modelStatus = ref<ModelStatus | null>(null)
const storageBusy = ref(false)
let unsubscribeStatus: (() => void) | null = null

const builtinModelState = computed(() => {
  const state = modelStatus.value?.state
  if (state === 'ready') return { label: '已安装', tone: 'ok' }
  if (state === 'downloading' || state === 'verifying' || state === 'starting') {
    return { label: '准备中', tone: 'warn' }
  }
  if (state === 'error') return { label: '需要处理', tone: 'bad' }
  return { label: '未安装', tone: 'warn' }
})

function formatBytes(value: number): string {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index > 2 ? 2 : 1)} ${units[index]}`
}

function applyConfig(config: ModelConfigPublic): void {
  provider.value = config.provider
  baseUrl.value = config.base_url
  model.value = config.model
  temperature.value = config.temperature
  maxTokens.value = config.max_tokens
  hasKey.value = config.has_api_key
  requiresKey.value = config.requires_key
  isLocal.value = config.is_local
}

function applyPreset(): void {
  const preset = providers.value[provider.value]
  if (!preset) return
  baseUrl.value = preset.base_url
  model.value = preset.model
  requiresKey.value = preset.requires_key
  isLocal.value = preset.local
  testResult.value = null
}

function payload(): Record<string, unknown> {
  const data: Record<string, unknown> = {
    provider: provider.value,
    base_url: baseUrl.value.trim(),
    model: model.value.trim(),
    temperature: temperature.value,
    max_tokens: maxTokens.value
  }
  if (apiKey.value.trim()) data.api_key = apiKey.value.trim()
  return data
}

async function test(): Promise<void> {
  testing.value = true
  error.value = ''
  testResult.value = null
  try {
    testResult.value = await window.eduanchor.call<ModelTestResult>(
      'settings.testModel',
      payload()
    )
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    testing.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  error.value = ''
  try {
    const response = await window.eduanchor.call<ModelSettingsResponse>(
      'settings.setModel',
      payload()
    )
    applyConfig(response.config)
    apiKey.value = ''
    emit('saved')
    emit('close')
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    saving.value = false
  }
}

async function openModelScope(): Promise<void> {
  await window.eduanchor.openExternal('https://www.modelscope.cn/models/Qwen/Qwen3-8B-GGUF')
}

async function chooseModelDirectory(): Promise<void> {
  storageBusy.value = true
  error.value = ''
  try {
    const status = await window.eduanchor.chooseModelDirectory()
    if (status) modelStatus.value = status
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    storageBusy.value = false
  }
}

async function downloadModel(): Promise<void> {
  storageBusy.value = true
  error.value = ''
  try {
    modelStatus.value = await window.eduanchor.downloadModel()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    storageBusy.value = false
  }
}

async function openModelFolder(): Promise<void> {
  try {
    await window.eduanchor.openModelFolder()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

onMounted(async () => {
  unsubscribeStatus = window.eduanchor.onModelStatus((status) => {
    modelStatus.value = status
  })
  try {
    const [response, status] = await Promise.all([
      window.eduanchor.call<ModelSettingsResponse>('settings.getModel'),
      window.eduanchor.modelStatus()
    ])
    providers.value = response.providers
    applyConfig(response.config)
    modelStatus.value = status
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  unsubscribeStatus?.()
})
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal settings-modal">
      <div class="modal-head">
        <div>
          <p class="eyebrow">MODEL PROVIDER</p>
          <h2>选择生成模型</h2>
        </div>
        <button class="ghost" @click="emit('close')">关闭</button>
      </div>

      <p class="muted settings-intro">
        默认使用项目内置的 Qwen3-8B Q4_K_M 与 llama.cpp，不依赖 Ollama；也可以切换到
        Ollama、vLLM 或任意 OpenAI 兼容厂商。所有配置仅保存在本机数据目录。
      </p>

      <div v-if="loading" class="loading">正在读取模型配置…</div>

      <template v-else>
        <section v-if="modelStatus" class="model-storage">
          <div class="model-storage-head">
            <div>
              <p class="eyebrow">BUILT-IN MODEL</p>
              <h3>内置模型存储</h3>
            </div>
            <span class="pill" :class="builtinModelState.tone">{{ builtinModelState.label }}</span>
          </div>

          <p class="muted model-storage-copy">
            首次使用会自动从 Hugging Face 镜像下载 Qwen3-8B Q4_K_M（约 5.0 GB），
            下载后可完全离线运行。你可以随时更改存储位置；已有模型会一起迁移。
          </p>

          <div v-if="modelStatus.state === 'downloading'" class="model-progress">
            <div class="model-progress-track">
              <div class="model-progress-fill" :style="{ width: `${modelStatus.percent.toFixed(1)}%` }"></div>
            </div>
            <div class="model-progress-meta">
              <span>{{ modelStatus.percent.toFixed(1) }}%</span>
              <span>
                {{ formatBytes(modelStatus.downloadedBytes) }} / {{ formatBytes(modelStatus.totalBytes) }}
              </span>
              <span>{{ formatBytes(modelStatus.bytesPerSecond) }}/s</span>
            </div>
          </div>
          <div v-else-if="modelStatus.state === 'verifying'" class="model-progress-note">
            下载完成，正在校验模型完整性…
          </div>
          <div v-else-if="modelStatus.state === 'starting'" class="model-progress-note">
            模型已就绪，正在启动本地推理服务…
          </div>

          <div class="model-path">
            <span>模型目录</span>
            <code>{{ modelStatus.directory || '—' }}</code>
          </div>
          <p v-if="modelStatus.error" class="model-error">{{ modelStatus.error }}</p>

          <div class="model-storage-actions">
            <button class="ghost" :disabled="storageBusy" @click="chooseModelDirectory">
              {{ storageBusy ? '处理中…' : '更改存储位置' }}
            </button>
            <button class="ghost" @click="openModelFolder">打开目录</button>
            <div class="spacer"></div>
            <button
              v-if="!modelStatus.installed || modelStatus.state === 'error'"
              class="primary"
              :disabled="storageBusy"
              @click="downloadModel"
            >
              {{ modelStatus.state === 'downloading' ? '继续下载' : '下载模型' }}
            </button>
          </div>
        </section>

        <h4>模型服务</h4>
        <label class="field">
          <span>服务商</span>
          <select v-model="provider" class="select wide" @change="applyPreset">
            <option v-for="(info, key) in providers" :key="key" :value="key">
              {{ info.label }}
            </option>
          </select>
        </label>

        <label class="field">
          <span>Base URL</span>
          <input v-model="baseUrl" class="input" placeholder="https://…/v1" />
        </label>

        <label class="field">
          <span>模型名</span>
          <input v-model="model" class="input" placeholder="qwen3-8b / deepseek-chat / qwen-plus" />
        </label>

        <label class="field">
          <span>API Key</span>
          <input
            v-model="apiKey"
            class="input"
            type="password"
            autocomplete="off"
            :placeholder="hasKey ? '已保存，留空保持不变' : requiresKey ? '输入厂商 API Key' : '本地服务可留空'"
          />
        </label>

        <div class="field-row">
          <label class="field">
            <span>Temperature</span>
            <input v-model.number="temperature" class="input" type="number" min="0" max="2" step="0.05" />
          </label>
          <label class="field">
            <span>Max tokens</span>
            <input v-model.number="maxTokens" class="input" type="number" min="64" max="8192" step="64" />
          </label>
        </div>

        <p class="hint">
          本地向量仍使用哈希降级；如需 BGE-M3，请参考 README 安装 <code>models</code> 额外依赖。
          <span v-if="isLocal">当前端点在本地，教材与问答不会离开本机。</span>
          <span v-else>当前为远程厂商 API，教材片段会发送到该服务商，请确认合规。</span>
        </p>

        <div v-if="testResult" class="test-result" :class="{ ok: testResult.ok, bad: !testResult.ok }">
          {{ testResult.ok ? '连接成功' : '连接失败' }} · {{ testResult.message }}
          · {{ testResult.latency_ms.toFixed(0) }} ms
        </div>
        <p v-if="error" class="error-banner">{{ error }}</p>

        <div class="settings-actions">
          <button class="ghost" @click="openModelScope">ModelScope Qwen3-8B-GGUF</button>
          <div class="spacer"></div>
          <button class="ghost" :disabled="testing" @click="test">
            {{ testing ? '测试中…' : '测试连接' }}
          </button>
          <button class="primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存并启用' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
