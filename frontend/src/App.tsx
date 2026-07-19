import { useState } from 'react'
import { AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from '@azure/msal-react'
import { apiBaseUrl, apiLoginRequest } from './authConfig'
import { acquireApiToken } from './apiAuth'
import { Chat } from './Chat'
import { Documents } from './Documents'
import './App.css'

interface Profile {
  id: string
  display_name: string
  mail: string | null
  user_principal_name: string
}

function App() {
  const { instance, accounts } = useMsal()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)

  const signIn = () => instance.loginRedirect(apiLoginRequest)
  const signOut = () => instance.logoutRedirect()

  const fetchMe = async () => {
    setError(null)
    try {
      const tokenResponse = await acquireApiToken(instance, accounts[0])
      const response = await fetch(`${apiBaseUrl}/me`, {
        headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
      })
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      setProfile(await response.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

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
            <h2>Account</h2>
            <button className="btn" onClick={fetchMe}>
              Fetch Graph profile
            </button>
          </div>
          {error && <p className="error-text">{error}</p>}
          {profile && <pre className="profile-json">{JSON.stringify(profile, null, 2)}</pre>}
        </section>

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
          {accounts[0] && <Chat instance={instance} account={accounts[0]} />}
        </section>
      </AuthenticatedTemplate>
    </div>
  )
}

export default App
