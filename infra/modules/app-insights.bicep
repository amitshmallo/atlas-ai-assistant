param name string
param location string
param tags object
param logAnalyticsWorkspaceId string

@description('The connection string is written directly into this Key Vault as a secret rather than returned as a module output — Bicep persists module outputs in plaintext in deployment history (same lesson as the Redis connection string in modules/redis.bicep).')
param keyVaultName string

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspaceId
    IngestionMode: 'LogAnalytics'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource connectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'appinsights-connection-string'
  properties: {
    value: appInsights.properties.ConnectionString
  }
}

output name string = appInsights.name
output id string = appInsights.id
