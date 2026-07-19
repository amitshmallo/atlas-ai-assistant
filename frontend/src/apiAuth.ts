import {
  InteractionRequiredAuthError,
  type AccountInfo,
  type IPublicClientApplication,
} from '@azure/msal-browser'
import { apiLoginRequest } from './authConfig'

export async function acquireApiToken(instance: IPublicClientApplication, account: AccountInfo) {
  try {
    return await instance.acquireTokenSilent({ ...apiLoginRequest, account })
  } catch (silentError) {
    if (silentError instanceof InteractionRequiredAuthError) {
      return await instance.acquireTokenPopup(apiLoginRequest)
    }
    throw silentError
  }
}
