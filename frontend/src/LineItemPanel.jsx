import { money } from './api'

export default function LineItemPanel({ lineItems, loading }) {
  if (!lineItems.length) {
    return loading ? <p className="muted">Loading…</p> : <p className="empty">No line items for this organization.</p>
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Call</th>
            <th>Investor</th>
            <th>Reference</th>
            <th className="num">Called</th>
            <th className="num">Funded</th>
            <th className="num">Remaining</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {lineItems.map((item) => (
            <tr key={item.id}>
              <td className="nowrap">
                #{item.capital_call}
                <div className="muted small">due {item.due_date}</div>
              </td>
              <td>{item.investor}</td>
              <td>{item.expected_reference}</td>
              <td className="num">{money(item.amount_called)}</td>
              <td className="num">{money(item.amount_funded)}</td>
              <td className="num">{money(item.amount_remaining)}</td>
              <td><span className={`badge ${item.status}`}>{item.status.replace('_', ' ')}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
