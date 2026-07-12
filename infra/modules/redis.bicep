param name string
param location string
param tags object

@description('Key Vault to write the redis-url secret into directly — the raw access key is never returned as a module output, since Bicep module outputs are persisted in plaintext in deployment history.')
param keyVaultName string

resource redis 'Microsoft.Cache/redis@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource redisUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'redis-url'
  properties: {
    value: 'rediss://:${redis.listKeys().primaryKey}@${redis.properties.hostName}:${redis.properties.sslPort}/0'
  }
}

output hostName string = redis.properties.hostName
output sslPort int = redis.properties.sslPort
output name string = redis.name
