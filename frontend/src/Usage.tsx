import { useEffect, useState } from 'react'
import type { AccountInfo, IPublicClientApplication } from '@azure/msal-browser'
import { apiBaseUrl } from './authConfig'
import { acquireApiToken } from './apiAuth'

interface UsageSummary {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated_cost_usd: number
  turn_count: number
}

// Refreshed whenever a chat turn finishes (see App.tsx's onChatTurnComplete),
// not polled — usage only changes right after a turn, so polling would just
// waste requests between turns.
export function Usage({
  instance,
  account,
  refreshKey,
}: {
  instance: IPublicClientApplication
  account: AccountInfo
  refreshKey: number
}) {
  const [summary, setSummary] = useState<UsageSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const fetchSummary = async () => {
      try {
        const tokenResponse = await acquireApiToken(instance, account)
        const response = await fetch(`${apiBaseUrl}/usage/summary`, {
          headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
        })
        if (!response.ok) throw new Error(`API returned ${response.status}`)
        const data = await response.json()
        if (!cancelled) setSummary(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }
    fetchSummary()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  if (error) return <p className="error-text">{error}</p>
  if (!summary) return null

  return (
    <div className="usage-grid">
      <div className="usage-stat">
        <span className="usage-stat-value">{summary.turn_count}</span>
        <span className="usage-stat-label">Turns (30d)</span>
      </div>
      <div className="usage-stat">
        <span className="usage-stat-value">{summary.total_tokens.toLocaleString()}</span>
        <span className="usage-stat-label">Tokens</span>
      </div>
      <div className="usage-stat">
        <span className="usage-stat-value">${summary.estimated_cost_usd.toFixed(4)}</span>
        <span className="usage-stat-label">Est. cost</span>
      </div>
    </div>
  )
}
