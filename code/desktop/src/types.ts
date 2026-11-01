export interface DocumentInfo {
  id: string
  title: string
  path?: string | null
  created_at: string
  pages: number
  chunk_count: number
  card_count: number
  embed_backend: string
}

export interface SourceSpan {
  page: number
  bbox?: number[] | null
  quote: string
}

export interface KnowledgeCard {
  id: string
  doc_id: string
  title: string
  summary: string
  key_points: string[]
  source: SourceSpan
  tags: string[]
  kind: 'definition' | 'principle' | 'procedure' | 'example' | 'concept'
}

export interface Citation {
  chunk_id: string
  page: number
  quote: string
  bbox?: number[] | null
  score: number
}

export interface RetrievedChunk {
  chunk: {
    id: string
    doc_id: string
    ordinal: number
    text: string
    page: number
    bbox?: number[] | null
    heading?: string | null
  }
  score: number
  bm25: number
  dense: number
  rerank: number
}

export interface TraceStep {
  agent: string
  action: string
  detail: string
  elapsed_ms: number
}

export interface Answer {
  question: string
  doc_id: string
  created_at: string
  mode: 'explain' | 'socratic'
  answer: string
  refused: boolean
  reason: string
  citations: Citation[]
  evidence: RetrievedChunk[]
  support_rate: number
  coverage: number
  condition: string
  trace: TraceStep[]
  latency_ms: number
  session_id?: string | null
  llm: string
}

export interface ModelConfigPublic {
  provider: string
  base_url: string
  model: string
  temperature: number
  max_tokens: number
  timeout: number
  has_api_key: boolean
  is_local: boolean
  requires_key: boolean
}

export interface ProviderInfo {
  label: string
  base_url: string
  model: string
  requires_key: boolean
  local: boolean
}

export interface ModelSettingsResponse {
  config: ModelConfigPublic
  providers: Record<string, ProviderInfo>
}

export interface ModelTestResult {
  ok: boolean
  message: string
  latency_ms: number
}

export interface EngineStatus {
  engine: string
  llm: ModelConfigPublic & { available: boolean; name: string }
  embedder: { name: string; dim: number }
  settings: Record<string, unknown>
  counts: { documents: number; chunks: number; cards: number; sessions: number }
}

export interface EvalMetrics {
  n_in: number
  n_out: number
  support_rate: number
  hallucination_rate: number
  false_refusal_rate: number
  refusal_accuracy: number
  answer_rate_out: number
  relevance: number
  mean_latency_ms: number
  support_ci: number[]
}

export interface EvalResponse {
  results: Record<string, { metrics: EvalMetrics; records: unknown[] }>
  latex: string[]
  n: number
}

declare global {
  interface Window {
    eduanchor: {
      call: <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>
      pickTextbook: () => Promise<string[]>
      openExternal: (url: string) => Promise<boolean>
      info: () => Promise<Record<string, unknown>>
    }
  }
}
