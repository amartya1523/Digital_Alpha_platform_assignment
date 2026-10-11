import { useCallback, useEffect, useState } from 'react'
import { request } from './api'
import UploadPanel from './UploadPanel'
import TransactionTable from './TransactionTable'
import LineItemPanel from './LineItemPanel'

export default function App() {
  const [orgs, setOrgs] = useState([])
  const [org, setOrg] = useState('')
  const [transactions, setTransactions] = useState([])
  const [lineItems, setLineItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    request('/organizations/')
      .then((data) => {
        setOrgs(data)
        if (data.length) setOrg(data[0].slug)
      })
      .catch((e) => setError(e.message))
  }, [])

  const refresh = useCallback(async () => {
    if (!org) return
    setLoading(true)
    setError('')
    try {
      const [txns, items] = await Promise.all([
        request('/transactions/', { org }),
        request('/line-items/', { org }),
      ])
      setTransactions(txns)
      setLineItems(items)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [org])

  useEffect(() => {
    setTransactions([])
    setLineItems([])
    refresh()
  }, [refresh])

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>CallMatch</h1>
          <p className="muted">Match bank payments to capital calls</p>
        </div>
        <label className="org-switcher">
          Organization
          <select value={org} onChange={(e) => setOrg(e.target.value)} disabled={!orgs.length}>
            {orgs.map((o) => (
              <option key={o.slug} value={o.slug}>{o.name}</option>
            ))}
          </select>
        </label>
      </header>

      {error && <div className="alert error">{error}</div>}

      {org && (
        <>
          <UploadPanel key={org} org={org} onImported={refresh} />

          <section className="card">
            <div className="card-title">
              <h2>Transactions</h2>
              {loading && <span className="muted">Loading…</span>}
            </div>
            <TransactionTable org={org} transactions={transactions} loading={loading} onChange={refresh} />
          </section>

          <section className="card">
            <h2>Line items</h2>
            <LineItemPanel lineItems={lineItems} loading={loading} />
          </section>
        </>
      )}
    </div>
  )
}
