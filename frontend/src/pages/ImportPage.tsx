import { useImportRuns } from '../hooks/useImportRuns'
import StatusBadge from '../components/StatusBadge'

export default function ImportPage() {
  const { runs, error, refresh } = useImportRuns()

  return (
    <div>
      <h2>Import-Runs</h2>
      <button onClick={refresh}>Aktualisieren</button>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Dateien</th>
            <th>Fehler</th>
            <th>Erstellt</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td style={{ fontFamily: 'monospace', fontSize: '0.8em' }}>{run.id.slice(0, 8)}…</td>
              <td><StatusBadge status={run.status} /></td>
              <td>{run.file_count}</td>
              <td>{run.error_count > 0 ? <span style={{ color: 'red' }}>{run.error_count}</span> : 0}</td>
              <td>{new Date(run.created_at).toLocaleString('de-DE')}</td>
            </tr>
          ))}
          {runs.length === 0 && (
            <tr><td colSpan={5} style={{ textAlign: 'center', color: '#888' }}>Keine Import-Runs vorhanden</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
