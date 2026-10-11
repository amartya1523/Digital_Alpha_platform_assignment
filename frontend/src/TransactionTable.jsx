import { useState } from 'react'
import { money, request } from './api'

export default function TransactionTable({ org, transactions, loading, onChange }) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')

  async function run(key, path) {
    setBusy(key)
    setError('')
    try {
      await request(path, { org, method: 'POST' })
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
      onChange()
    }
  }

  if (!transactions.length) {
    return loading ? null : <p className="empty">No transactions yet. Upload a bank statement to get started.</p>
  }

  return (
    <>
      {error && <div className="alert error">{error}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th className="num">Amount</th>
              <th>Status</th>
              <th>Suggested investor / reference</th>
              <th>Reason</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((txn) => {
              const matches = txn.matches.filter((m) => m.status !== 'rejected')
              const proposed = txn.matches.filter((m) => m.status === 'proposed')
              const canIgnore = txn.status === 'suggested' || txn.status === 'needs_review'

              return (
                <tr key={txn.id}>
                  <td className="nowrap">{txn.date}</td>
                  <td>
                    {txn.description}
                    <div className="muted small">{txn.bank_reference}</div>
                  </td>
                  <td className="num nowrap">{money(txn.amount)}</td>
                  <td><span className={`badge ${txn.status}`}>{txn.status.replace('_', ' ')}</span></td>
                  <td>
                    {matches.length === 0 && <span className="muted">—</span>}
                    {matches.map((m) => (
                      <div key={m.id}>
                        {m.investor} <span className="muted">· {m.expected_reference}</span>
                        {m.status === 'approved' && <span className="muted"> (approved)</span>}
                      </div>
                    ))}
                  </td>
                  <td className="reason">
                    {txn.review_reason && <div>{txn.review_reason}</div>}
                    {matches.map((m) => (
                      <div key={m.id} className="muted">{m.reason}</div>
                    ))}
                  </td>
                  <td className="actions">
                    {proposed.map((m) => (
                      <div key={m.id} className="action-row">
                        <button disabled={busy !== null} onClick={() => run(`approve-${m.id}`, `/matches/${m.id}/approve/`)}>
                          {busy === `approve-${m.id}` ? 'Approving…' : `Approve ${m.expected_reference}`}
                        </button>
                        <button className="secondary" disabled={busy !== null} onClick={() => run(`reject-${m.id}`, `/matches/${m.id}/reject/`)}>
                          {busy === `reject-${m.id}` ? 'Rejecting…' : 'Reject'}
                        </button>
                      </div>
                    ))}
                    {canIgnore && (
                      <button className="secondary" disabled={busy !== null} onClick={() => run(`ignore-${txn.id}`, `/transactions/${txn.id}/ignore/`)}>
                        {busy === `ignore-${txn.id}` ? 'Ignoring…' : 'Ignore'}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
