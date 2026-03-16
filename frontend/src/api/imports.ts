import apiClient from './client'
import type { ImportRun } from '../types/runs'

export async function listImportRuns(): Promise<ImportRun[]> {
  const res = await apiClient.get<ImportRun[]>('/import-runs')
  return res.data
}

export async function getImportRun(id: string): Promise<ImportRun> {
  const res = await apiClient.get<ImportRun>(`/import-runs/${id}`)
  return res.data
}

export async function createImportRun(sourceId: string, idempotencyKey?: string): Promise<ImportRun> {
  const res = await apiClient.post<ImportRun>('/import-runs', {
    source_id: sourceId,
    idempotency_key: idempotencyKey,
  })
  return res.data
}
