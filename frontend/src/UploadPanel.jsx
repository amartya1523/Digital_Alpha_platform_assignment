import { useState } from 'react'
import { request } from './api'

export default function UploadPanel({ org, onImported }) {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!file) return

    const body = new FormData()
    body.append('file', file)

    setUploading(true)
    setError('')
    setSummary(null)
    try {
      setSummary(await request('/transactions/import/', { org, method: 'POST', body }))
      onImported()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="card">
      <h2>Import bank statement</h2>
      <form className="upload" onSubmit={handleSubmit}>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files[0] || null)} />
        <button type="submit" disabled={!file || uploading}>
          {uploading ? 'Uploading…' : 'Upload CSV'}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}

      {summary && (
        <div className="summary">
          <div className="stats">
            <span><strong>{summary.imported}</strong> imported</span>
            <span><strong>{summary.duplicates}</strong> duplicates</span>
            <span><strong>{summary.errors.length}</strong> errors</span>
          </div>
          {(summary.errors.length > 0 || summary.duplicate_rows.length > 0) && (
            <ul className="row-errors">
              {summary.errors.map((err) => (
                <li key={`e${err.line}`}>Line {err.line}: {err.message}</li>
              ))}
              {summary.duplicate_rows.map((dup) => (
                <li key={`d${dup.line}`} className="muted">
                  Line {dup.line}: duplicate bank reference {dup.reference}, skipped.
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
