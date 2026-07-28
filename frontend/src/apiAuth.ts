import type { AccountInfo, AuthenticationResult, IPublicClientApplication } from '@azure/msal-browser'
import { apiLoginRequest } from './authConfig'

// Sidebar, Documents, Chat, and Usage each acquire a token independently on
// mount. If acquireTokenSilent needs a fallback, MSAL only allows one
// interactive request at a time — a second concurrent call throws
// `interaction_in_progress`. Sharing one in-flight promise across all
// callers means only the first caller actually triggers silent/interactive
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
      // Falls back to interactive for any silent-acquisition failure, not
      // just InteractionRequiredAuthError — acquireTokenSilent's hidden
      // iframe also throws a plain BrowserAuthError ("timed_out"/
      // monitor_window_timeout) when third-party cookies are blocked,
      // which browsers do by default.
      //
      // This fallback fires from component-mount effects, not from a
      // click handler, so a popup here is exactly the case browsers'
      // popup blockers exist to stop (`popup_window_error`) — there's no
      // user gesture backing it. acquireTokenRedirect instead navigates
      // the whole page away and back, which isn't subject to popup
      // blocking, matching the redirect flow already used for sign-in.
      await instance.acquireTokenRedirect(apiLoginRequest)
      // acquireTokenRedirect navigates away; execution never reaches here
      // in practice, but it returns void, so this satisfies the type.
      return new Promise<AuthenticationResult>(() => {})
    }
  })()

  try {
    return await pendingTokenRequest
  } finally {
    pendingTokenRequest = null
  }
}
