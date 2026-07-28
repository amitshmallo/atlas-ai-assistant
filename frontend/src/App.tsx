import { useState } from 'react'
import { AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from '@azure/msal-react'
import { apiLoginRequest } from './authConfig'
import { Chat } from './Chat'
import { Documents } from './Documents'
import { Usage } from './Usage'
import './App.css'

function App() {
  const { instance, accounts } = useMsal()
  const [usageRefreshKey, setUsageRefreshKey] = useState(0)

  const signIn = () => instance.loginRedirect(apiLoginRequest)
  const signOut = () => instance.logoutRedirect()

  return (
    <div className="app">
      <UnauthenticatedTemplate>
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
      </UnauthenticatedTemplate>

      <AuthenticatedTemplate>
        <header className="app-header">
          <div>
            <h1>Atlas</h1>
            <p className="tagline">Your AI executive assistant</p>
          </div>
          <div className="app-user">
            <span>{accounts[0]?.username}</span>
            <button className="btn btn-ghost" onClick={signOut}>
              Sign out
            </button>
          </div>
        </header>

        <section className="panel">
          <div className="panel-header">
            <h2>Documents</h2>
          </div>
          {accounts[0] && <Documents instance={instance} account={accounts[0]} />}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Chat</h2>
          </div>
          {accounts[0] && (
            <Chat
              instance={instance}
              account={accounts[0]}
              onTurnComplete={() => setUsageRefreshKey((key) => key + 1)}
            />
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Usage</h2>
          </div>
          {accounts[0] && <Usage instance={instance} account={accounts[0]} refreshKey={usageRefreshKey} />}
        </section>
      </AuthenticatedTemplate>
    </div>
  )
}

export default App
