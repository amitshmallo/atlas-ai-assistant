import type { AccountInfo, AuthenticationResult, IPublicClientApplication } from '@azure/msal-browser'
import { apiLoginRequest } from './authConfig'

// Sidebar, Documents, Chat, and Usage each acquire a token independently on
// mount. If acquireTokenSilent needs a fallback, MSAL only allows one
// interactive request (popup/redirect) at a time — a second concurrent
// call throws `interaction_in_progress`, and two popups racing each other
// can also trip `popup_window_error`. Sharing one in-flight promise across
// all callers means only the first caller actually triggers silent/popup
// acquisition; everyone else just awaits its result.
let pendingTokenRequest: Promise<AuthenticationResult> | null = null

export async function acquireApiToken(
  instance: IPublicClientApplication,
  account: AccountInfo
): Promise<AuthenticationResult> {
  if (pendingTokenRequest) return pendingTokenRequest

  pendingTokenRequest = (async () => {
    try {
      return await instance.acquireTokenSilent({ ...apiLoginRequest, account })
    } catch {
      // Falls back to interactive for any silent-acquisition failure, not just
      // InteractionRequiredAuthError — acquireTokenSilent's hidden iframe also
      // throws a plain BrowserAuthError ("timed_out"/monitor_window_timeout)
      // when third-party cookies are blocked, which browsers do by default
      // and which only bites on a real cross-origin deployment, not localhost.
      return await instance.acquireTokenPopup(apiLoginRequest)
    }
  })()

  try {
    return await pendingTokenRequest
  } finally {
    pendingTokenRequest = null
  }
}
