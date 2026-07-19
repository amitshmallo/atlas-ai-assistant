import { useState } from 'react'
import type { AccountInfo, IPublicClientApplication } from '@azure/msal-browser'
import { apiBaseUrl } from './authConfig'
import { acquireApiToken } from './apiAuth'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface StoredMessage {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls: { id: string; name: string; arguments: Record<string, unknown> }[] | null
  tool_call_id: string | null
  name: string | null
}

interface CalendarEventProposal {
  subject: string
  start: string
  end: string
  attendees: string[]
}

// After a turn completes, look back through history (only within this
// turn, i.e. after the most recent user message) for a propose_calendar_event
// tool result — that's the model surfacing a proposal for the user to
// review, never something it created itself.
function findPendingProposal(history: StoredMessage[]): CalendarEventProposal | null {
  const lastUserIndex = history.map((m) => m.role).lastIndexOf('user')
  for (let i = history.length - 1; i > lastUserIndex; i--) {
    const message = history[i]
    if (message.role === 'tool' && message.name === 'propose_calendar_event' && message.content) {
      try {
        const parsed = JSON.parse(message.content)
        return {
          subject: parsed.subject,
          start: parsed.start,
          end: parsed.end,
          attendees: parsed.attendees ?? [],
        }
      } catch {
        return null
      }
    }
  }
  return null
}

export function Chat({
  instance,
  account,
}: {
  instance: IPublicClientApplication
  account: AccountInfo
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  // Kept in memory only — Phase 5 proves persistence lives server-side
  // (Postgres + Redis), not that the browser tab remembers it across reloads.
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [pendingProposal, setPendingProposal] = useState<CalendarEventProposal | null>(null)
  const [confirmStatus, setConfirmStatus] = useState<string | null>(null)

  const checkForPendingProposal = async (currentConversationId: string) => {
    const tokenResponse = await acquireApiToken(instance, account)
    const response = await fetch(`${apiBaseUrl}/chat/${currentConversationId}/messages`, {
      headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
    })
    if (!response.ok) return
    const history: StoredMessage[] = await response.json()
    setPendingProposal(findPendingProposal(history))
  }

  const send = async () => {
    if (!input.trim() || isStreaming) return
    setError(null)
    setConfirmStatus(null)

    const userMessage = input
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }, { role: 'assistant', content: '' }])
    setInput('')
    setIsStreaming(true)

    try {
      const tokenResponse = await acquireApiToken(instance, account)

      const response = await fetch(`${apiBaseUrl}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${tokenResponse.accessToken}`,
        },
        body: JSON.stringify({ conversation_id: conversationId, message: userMessage }),
      })
      if (!response.ok || !response.body) {
        throw new Error(`API returned ${response.status}`)
      }

      const returnedConversationId = response.headers.get('X-Conversation-Id')
      if (returnedConversationId) {
        setConversationId(returnedConversationId)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let assistantText = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        assistantText += decoder.decode(value, { stream: true })
        setMessages((prev) => [...prev.slice(0, -1), { role: 'assistant', content: assistantText }])
      }

      if (returnedConversationId) {
        await checkForPendingProposal(returnedConversationId)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsStreaming(false)
    }
  }

  const confirmProposal = async () => {
    if (!pendingProposal) return
    setConfirmStatus('Creating...')
    try {
      const tokenResponse = await acquireApiToken(instance, account)
      const response = await fetch(`${apiBaseUrl}/calendar/events`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${tokenResponse.accessToken}`,
        },
        body: JSON.stringify(pendingProposal),
      })
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`)
      }
      setConfirmStatus('Event created — check your calendar.')
      setPendingProposal(null)
    } catch (err) {
      setConfirmStatus(null)
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="chat">
      {conversationId && <p className="chat-conversation-id">Conversation: {conversationId}</p>}

      <div className="chat-history">
        {messages.map((message, index) => (
          <p key={index} className={`chat-message chat-message-${message.role}`}>
            <strong>{message.role === 'user' ? 'You' : 'Atlas'}:</strong> {message.content}
          </p>
        ))}
      </div>

      <div className="chat-input">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && send()}
          placeholder="Ask Atlas something..."
          disabled={isStreaming}
        />
        <button onClick={send} disabled={isStreaming}>
          {isStreaming ? 'Sending...' : 'Send'}
        </button>
      </div>

      {pendingProposal && (
        <div className="chat-proposal">
          <p>
            <strong>Proposed event:</strong> {pendingProposal.subject}
            <br />
            {pendingProposal.start} → {pendingProposal.end}
            {pendingProposal.attendees.length > 0 && <> · {pendingProposal.attendees.join(', ')}</>}
          </p>
          <button onClick={confirmProposal}>Confirm — create in calendar</button>
          <button onClick={() => setPendingProposal(null)}>Dismiss</button>
        </div>
      )}
      {confirmStatus && <p className="chat-conversation-id">{confirmStatus}</p>}

      {error && <p style={{ color: 'red' }}>{error}</p>}
    </div>
  )
}
