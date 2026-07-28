import { useEffect, useState } from 'react'
import type { AccountInfo, IPublicClientApplication } from '@azure/msal-browser'
import { apiBaseUrl } from './authConfig'
import { acquireApiToken } from './apiAuth'

interface ConversationSummary {
  id: string
  title: string
  updated_at: string
}

export type View = { type: 'chat'; conversationId: string | null } | { type: 'settings' }

// refreshKey bumps whenever a turn creates a brand-new conversation (see
// Chat's onConversationCreated) — the sidebar has no other way to know a
// new one exists, since it doesn't own conversation state itself.
export function Sidebar({
  instance,
  account,
  view,
  onSelectView,
  onNewChat,
  refreshKey,
}: {
  instance: IPublicClientApplication
  account: AccountInfo
  view: View
  onSelectView: (view: View) => void
  onNewChat: () => void
  refreshKey: number
}) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const tokenResponse = await acquireApiToken(instance, account)
        const response = await fetch(`${apiBaseUrl}/chat/conversations`, {
          headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
        })
        if (!response.ok) throw new Error(`API returned ${response.status}`)
        const data = await response.json()
        if (!cancelled) setConversations(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <h1>Atlas</h1>
        <p className="tagline">Your AI executive assistant</p>
      </div>

      <button type="button" className="sidebar-new-chat" onClick={onNewChat}>
        + New chat
      </button>

      <div className="sidebar-section-label">Recent chats</div>
      <ul className="sidebar-conversations">
        {conversations.length === 0 && <li className="sidebar-empty">No conversations yet.</li>}
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              className={`sidebar-conversation-item${
                view.type === 'chat' && view.conversationId === conversation.id ? ' sidebar-item-active' : ''
              }`}
              title={conversation.title}
              onClick={() => onSelectView({ type: 'chat', conversationId: conversation.id })}
            >
              {conversation.title}
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="error-text">{error}</p>}

      <div className="sidebar-footer">
        <button
          type="button"
          className={`sidebar-settings-item${view.type === 'settings' ? ' sidebar-item-active' : ''}`}
          onClick={() => onSelectView({ type: 'settings' })}
        >
          ⚙ Settings
        </button>
      </div>
    </nav>
  )
}
