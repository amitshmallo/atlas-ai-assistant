import { useState } from 'react'
import { AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from '@azure/msal-react'
import { apiLoginRequest } from './authConfig'
import { Chat } from './Chat'
import { Documents } from './Documents'
import { Settings } from './Settings'
import { Sidebar, type View } from './Sidebar'
import './App.css'

function App() {
  const { instance, accounts } = useMsal()
  const [usageRefreshKey, setUsageRefreshKey] = useState(0)
  const [conversationsRefreshKey, setConversationsRefreshKey] = useState(0)
  const [view, setView] = useState<View>({ type: 'chat', conversationId: null })
  // Bumped only by the sidebar's "+ New chat" button — forces Chat to
  // remount into a blank session even when already viewing an unsaved new
  // chat (view.conversationId is null in both cases, so the key alone
  // wouldn't change without this).
  const [newChatNonce, setNewChatNonce] = useState(0)

  const signIn = () => instance.loginRedirect(apiLoginRequest)
  const signOut = () => instance.logoutRedirect()

  return (
    <div className="app-shell">
      <UnauthenticatedTemplate>
        <div className="app">
          <header className="app-header">
            <div>
              <h1>Atlas</h1>
              <p className="tagline">Your AI executive assistant</p>
            </div>
          </header>

          <div className="signin-card">
            <h2>Sign in to get started</h2>
            <p>Atlas needs your Microsoft account to read email, manage your calendar, and answer questions about your documents.</p>
            <button className="btn btn-primary" onClick={signIn}>
              Sign in with Microsoft
            </button>
          </div>
        </div>
      </UnauthenticatedTemplate>

      <AuthenticatedTemplate>
        {accounts[0] && (
          <Sidebar
            instance={instance}
            account={accounts[0]}
            view={view}
            onSelectView={setView}
            onNewChat={() => {
              setView({ type: 'chat', conversationId: null })
              setNewChatNonce((n) => n + 1)
            }}
            refreshKey={conversationsRefreshKey}
          />
        )}

        <div className="app">
          <header className="app-header">
            <div>
              <h1>Atlas</h1>
              <p className="tagline">Your AI executive assistant</p>
            </div>
          </header>

          {view.type === 'settings' && accounts[0] && (
            <Settings
              instance={instance}
              account={accounts[0]}
              usageRefreshKey={usageRefreshKey}
              onSignOut={signOut}
            />
          )}

          {view.type === 'chat' && accounts[0] && (
            <>
              <section className="panel">
                <div className="panel-header">
                  <h2>Documents</h2>
                </div>
                <Documents instance={instance} account={accounts[0]} />
              </section>

              <section className="panel">
                <div className="panel-header">
                  <h2>Chat</h2>
                </div>
                <Chat
                  // Remount on conversation switch so Chat's internal
                  // state (messages, streaming, proposal) starts fresh
                  // rather than trying to reconcile in place.
                  key={view.conversationId ?? `new-${newChatNonce}`}
                  instance={instance}
                  account={accounts[0]}
                  initialConversationId={view.conversationId}
                  onTurnComplete={() => setUsageRefreshKey((key) => key + 1)}
                  onConversationCreated={() => setConversationsRefreshKey((key) => key + 1)}
                />
              </section>
            </>
          )}
        </div>
      </AuthenticatedTemplate>
    </div>
  )
}

export default App
