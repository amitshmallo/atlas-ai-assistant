import { useState } from 'react'
import {
  InteractionRequiredAuthError,
  type AccountInfo,
  type IPublicClientApplication,
} from '@azure/msal-browser'
import { apiBaseUrl, apiLoginRequest } from './authConfig'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

async function acquireApiToken(instance: IPublicClientApplication, account: AccountInfo) {
  try {
    return await instance.acquireTokenSilent({ ...apiLoginRequest, account })
  } catch (silentError) {
    if (silentError instanceof InteractionRequiredAuthError) {
      return await instance.acquireTokenPopup(apiLoginRequest)
    }
    throw silentError
  }
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

  const send = async () => {
    if (!input.trim() || isStreaming) return
    setError(null)

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
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsStreaming(false)
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

      {error && <p style={{ color: 'red' }}>{error}</p>}
    </div>
  )
}
