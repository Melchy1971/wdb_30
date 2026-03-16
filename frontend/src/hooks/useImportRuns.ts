import { useEffect, useRef, useState } from 'react'
import { listImportRuns } from '../api/imports'
import type { ImportRun } from '../types/runs'

const POLL_INTERVAL_MS = 2_000
const ACTIVE_STATUSES = new Set(['pending', 'running'])

export function useImportRuns() {
  const [runs, setRuns] = useState<ImportRun[]>([])
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetch = async () => {
    try {
      const data = await listImportRuns()
      setRuns(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler')
    }
  }

  useEffect(() => {
    fetch()
    intervalRef.current = setInterval(() => {
      const hasActive = runs.some((r) => ACTIVE_STATUSES.has(r.status))
      if (hasActive) fetch()
    }, POLL_INTERVAL_MS)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [runs])

  return { runs, error, refresh: fetch }
}
