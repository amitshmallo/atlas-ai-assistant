param name string
param location string
param tags object

@description('Key Vault to write the redis-url secret into directly — the raw access key is never returned as a module output, since Bicep module outputs are persisted in plaintext in deployment history.')
param keyVaultName string

// Classic Azure Cache for Redis (Microsoft.Cache/redis) is retired for new
// deployments — this is Azure Managed Redis, the replacement service.
resource redis 'Microsoft.Cache/redisEnterprise@2024-09-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Balanced_B0'
  }
}

resource redisDatabase 'Microsoft.Cache/redisEnterprise/databases@2024-09-01-preview' = {
  parent: redis
  name: 'default'
  properties: {
    clusteringPolicy: 'EnterpriseCluster'
    evictionPolicy: 'NoEviction'
    port: 10000
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource redisUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'redis-url'
  properties: {
    value: 'rediss://:${redisDatabase.listKeys().primaryKey}@${redis.properties.hostName}:${redisDatabase.properties.port}/0'
  }
}

output hostName string = redis.properties.hostName
output sslPort int = redisDatabase.properties.port
output name string = redis.name
