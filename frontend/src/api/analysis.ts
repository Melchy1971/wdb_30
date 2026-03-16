import apiClient from './client'
import type { AnalysisRun } from '../types/runs'

export async function listAnalysisRuns(): Promise<AnalysisRun[]> {
  const res = await apiClient.get<AnalysisRun[]>('/analysis-runs')
  return res.data
}

export async function getAnalysisRun(id: string): Promise<AnalysisRun> {
  const res = await apiClient.get<AnalysisRun>(`/analysis-runs/${id}`)
  return res.data
}

export async function createAnalysisRun(sourceId: string, idempotencyKey?: string): Promise<AnalysisRun> {
  const res = await apiClient.post<AnalysisRun>('/analysis-runs', {
    source_id: sourceId,
    idempotency_key: idempotencyKey,
  })
  return res.data
}
