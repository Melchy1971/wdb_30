import type { ImportRunStatus, AnalysisRunStatus } from '../types/runs'

type Status = ImportRunStatus | AnalysisRunStatus

const COLOR: Record<string, string> = {
  pending: '#888',
  running: '#1a7abf',
  completed: '#2a9d2a',
  partial: '#e08000',
  failed: '#cc2222',
  cancelled: '#888',
  stale: '#aaa',
  draft: '#888',
  approved: '#2a9d2a',
  rejected: '#cc2222',
}

interface Props {
  status: Status
}

export default function StatusBadge({ status }: Props) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: '0.8em',
        fontWeight: 600,
        color: '#fff',
        background: COLOR[status] ?? '#888',
        textTransform: 'uppercase',
      }}
    >
      {status}
    </span>
  )
}
