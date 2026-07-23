param name string
param location string
param tags object
param logAnalyticsWorkspaceId string
param infrastructureSubnetId string

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: last(split(logAnalyticsWorkspaceId, '/'))
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      // internal: false (the default) — the environment keeps a public
      // static IP so the API's ingress stays internet-reachable. VNet
      // integration here is about letting the API reach privately
      // networked Postgres/Search/AI Foundry, not about hiding the API
      // itself — that would break the whole point of a browser-facing app.
    }
  }
}

output environmentId string = environment.id
output name string = environment.name
output defaultDomain string = environment.properties.defaultDomain
