import type { AccountInfo, IPublicClientApplication } from '@azure/msal-browser'
import { apiLoginRequest } from './authConfig'

export async function acquireApiToken(instance: IPublicClientApplication, account: AccountInfo) {
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
}
