import type { AccountInfo, IPublicClientApplication } from '@azure/msal-browser'
import { Usage } from './Usage'

export function Settings({
  instance,
  account,
  usageRefreshKey,
  onSignOut,
}: {
  instance: IPublicClientApplication
  account: AccountInfo
  usageRefreshKey: number
  onSignOut: () => void
}) {
  return (
    <div className="settings">
      <section className="panel">
        <div className="panel-header">
          <h2>Account</h2>
        </div>
        <p className="settings-account-email">{account.username}</p>
        <button className="btn btn-ghost" onClick={onSignOut}>
          Disconnect
        </button>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Usage</h2>
        </div>
        <Usage instance={instance} account={account} refreshKey={usageRefreshKey} />
      </section>
    </div>
  )
}
