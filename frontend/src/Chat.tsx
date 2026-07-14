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

  const send = async () => {
    if (!input.trim() || isStreaming) return
    setError(null)

    const nextMessages: ChatMessage[] = [...messages, { role: 'user', content: input }]
    setMessages([...nextMessages, { role: 'assistant', content: '' }])
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
        body: JSON.stringify({ messages: nextMessages }),
      })
      if (!response.ok || !response.body) {
        throw new Error(`API returned ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let assistantText = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        assistantText += decoder.decode(value, { stream: true })
        setMessages([...nextMessages, { role: 'assistant', content: assistantText }])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <div className="chat">
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
