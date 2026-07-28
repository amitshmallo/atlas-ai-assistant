import { useEffect, useRef, useState } from 'react'
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

interface EmailSendProposal {
  to: string
  subject: string
  body: string
  attachment_filename: string | null
}

type PendingProposal =
  | { type: 'calendar'; data: CalendarEventProposal }
  | { type: 'email'; data: EmailSendProposal }

// After a turn completes, look back through history (only within this
// turn, i.e. after the most recent user message) for a propose_* tool
// result — that's the model surfacing a proposal for the user to review,
// never something it created/sent itself. Only the most recent one (if
// the model proposed more than one) is shown, matching how only one
// proposal card renders at a time.
function findPendingProposal(history: StoredMessage[]): PendingProposal | null {
  const lastUserIndex = history.map((m) => m.role).lastIndexOf('user')
  for (let i = history.length - 1; i > lastUserIndex; i--) {
    const message = history[i]
    if (message.role !== 'tool' || !message.content) continue

    if (message.name === 'propose_calendar_event') {
      try {
        const parsed = JSON.parse(message.content)
        return {
          type: 'calendar',
          data: {
            subject: parsed.subject,
            start: parsed.start,
            end: parsed.end,
            attendees: parsed.attendees ?? [],
          },
        }
      } catch {
        return null
      }
    }

    if (message.name === 'propose_send_email') {
      try {
        const parsed = JSON.parse(message.content)
        return {
          type: 'email',
          data: {
            to: parsed.to,
            subject: parsed.subject,
            body: parsed.body,
            attachment_filename: parsed.attachment_filename ?? null,
          },
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
  const [pendingProposal, setPendingProposal] = useState<PendingProposal | null>(null)
  const [confirmStatus, setConfirmStatus] = useState<string | null>(null)
  const historyEndRef = useRef<HTMLDivElement>(null)

  // Fires on every message change, including in-place content updates to
  // the last (streaming) message, so the view tracks a reply as it's
  // still being written in, not just once it's done.
  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

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
    const isEmail = pendingProposal.type === 'email'
    setConfirmStatus(isEmail ? 'Sending...' : 'Creating...')
    try {
      const tokenResponse = await acquireApiToken(instance, account)
      const response = await fetch(`${apiBaseUrl}${isEmail ? '/email/send' : '/calendar/events'}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${tokenResponse.accessToken}`,
        },
        body: JSON.stringify(pendingProposal.data),
      })
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`)
      }
      setConfirmStatus(isEmail ? 'Email sent.' : 'Event created — check your calendar.')
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
        {messages.length === 0 && <p className="documents-empty">Ask Atlas about your email, calendar, or documents.</p>}
        {messages.map((message, index) => (
          <div key={index} className={`chat-message chat-message-${message.role}`}>
            <strong>{message.role === 'user' ? 'You' : 'Atlas'}</strong>
            <span>{message.content}</span>
          </div>
        ))}
        <div ref={historyEndRef} />
      </div>

      <div className="chat-input">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && send()}
          placeholder="Ask Atlas something..."
          disabled={isStreaming}
        />
        <button className="btn btn-primary" onClick={send} disabled={isStreaming}>
          {isStreaming ? 'Sending...' : 'Send'}
        </button>
      </div>

      {pendingProposal?.type === 'calendar' && (
        <div className="chat-proposal">
          <p>
            <strong>Proposed event:</strong> {pendingProposal.data.subject}
            <br />
            {pendingProposal.data.start} → {pendingProposal.data.end}
            {pendingProposal.data.attendees.length > 0 && <> · {pendingProposal.data.attendees.join(', ')}</>}
          </p>
          <div className="chat-proposal-actions">
            <button className="btn btn-primary" onClick={confirmProposal}>
              Confirm — create in calendar
            </button>
            <button className="btn btn-ghost" onClick={() => setPendingProposal(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {pendingProposal?.type === 'email' && (
        <div className="chat-proposal">
          <p>
            <strong>Proposed email</strong>
            <br />
            To: {pendingProposal.data.to}
            <br />
            Subject: {pendingProposal.data.subject}
            {pendingProposal.data.attachment_filename && (
              <>
                <br />
                Attachment: {pendingProposal.data.attachment_filename}
              </>
            )}
          </p>
          <p className="chat-proposal-body">{pendingProposal.data.body}</p>
          <div className="chat-proposal-actions">
            <button className="btn btn-primary" onClick={confirmProposal}>
              Confirm — send email
            </button>
            <button className="btn btn-ghost" onClick={() => setPendingProposal(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}
      {confirmStatus && <p className="chat-status-text">{confirmStatus}</p>}

      {error && <p className="error-text">{error}</p>}
    </div>
  )
}
