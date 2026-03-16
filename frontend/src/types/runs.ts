export type ImportRunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'cancelled'
  | 'stale'

export type AnalysisRunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'stale'

export type AnalysisResultStatus = 'draft' | 'approved' | 'rejected'

export interface ImportRun {
  id: string
  source_id: string
  run_type: string
  status: ImportRunStatus
  started_at: string | null
  finished_at: string | null
  error_text: string | null
  file_count: number
  success_count: number
  error_count: number
  idempotency_key: string | null
  created_at: string
  updated_at: string
}

export interface AnalysisResult {
  id: string
  analysis_run_id: string
  source_id: string
  status: AnalysisResultStatus
  result_type: string
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface AnalysisRun {
  id: string
  source_id: string
  run_type: string
  status: AnalysisRunStatus
  started_at: string | null
  finished_at: string | null
  error_text: string | null
  file_count: number
  success_count: number
  error_count: number
  idempotency_key: string | null
  results: AnalysisResult[]
  created_at: string
  updated_at: string
}
