import { useState } from 'react'
import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
  useMsal,
} from '@azure/msal-react'
import { InteractionRequiredAuthError } from '@azure/msal-browser'
import { apiBaseUrl, apiLoginRequest } from './authConfig'
import { Chat } from './Chat'
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
      const account = accounts[0]
      let tokenResponse
      try {
        tokenResponse = await instance.acquireTokenSilent({
          ...apiLoginRequest,
          account,
        })
      } catch (silentError) {
        if (silentError instanceof InteractionRequiredAuthError) {
          tokenResponse = await instance.acquireTokenPopup(apiLoginRequest)
        } else {
          throw silentError
        }
      }

      const response = await fetch(`${apiBaseUrl}/me`, {
        headers: { Authorization: `Bearer ${tokenResponse.accessToken}` },
      })
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`)
      }
      setProfile(await response.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="app">
      <h1>Atlas</h1>

      <UnauthenticatedTemplate>
        <button onClick={signIn}>Sign in with Microsoft</button>
      </UnauthenticatedTemplate>

      <AuthenticatedTemplate>
        <p>Signed in as {accounts[0]?.username}</p>
        <button onClick={fetchMe}>Fetch Graph profile via API</button>
        <button onClick={signOut}>Sign out</button>

        {error && <p style={{ color: 'red' }}>{error}</p>}
        {profile && <pre>{JSON.stringify(profile, null, 2)}</pre>}

        <hr />
        {accounts[0] && <Chat instance={instance} account={accounts[0]} />}
      </AuthenticatedTemplate>
    </div>
  )
}

export default App
