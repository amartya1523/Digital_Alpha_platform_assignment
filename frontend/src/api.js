// empty in dev (Vite proxies /api), the backend URL when deployed
const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export async function request(path, { org, method = 'GET', body } = {}) {
  const headers = org ? { 'X-Organization': org } : {}
  const res = await fetch(`${API_URL}/api${path}`, { method, headers, body })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`)
  }
  return data
}

const moneyFormat = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function money(value) {
  return moneyFormat.format(Number(value))
}
