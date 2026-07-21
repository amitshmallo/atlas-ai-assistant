targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name used to derive resource names and as the azd environment name')
param environmentName string

@description('Primary location for all resources')
param location string

@description('Postgres administrator password')
@secure()
param postgresAdminPassword string

@description('Entra ID tenant ID')
param entraTenantId string = ''

@description('Entra ID API app client ID')
param entraApiClientId string = ''

@description('Entra ID API app client secret')
@secure()
param entraApiClientSecret string = ''

@description('Principal ID of the identity running the deployment — azd injects this automatically so it can write Key Vault secrets under RBAC authorization')
param principalId string = ''

@description('Exact model version string for the gpt-5-mini deployment — check the AI Foundry portal or `az cognitiveservices account list-models` for the current value before deploying, since model versions get retired/replaced over time')
param aiFoundryModelVersion string

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
}
var databaseUrl = 'postgresql+asyncpg://atlasadmin:${postgresAdminPassword}@${postgres.outputs.fqdn}:5432/atlas'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'log-analytics'
  scope: resourceGroup
  params: {
    name: 'log-${resourceToken}'
    location: location
    tags: tags
  }
}

module containerRegistry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: resourceGroup
  params: {
    name: 'acr${resourceToken}'
    location: location
    tags: tags
  }
}

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  scope: resourceGroup
  params: {
    name: 'kv-${resourceToken}'
    location: location
    tags: tags
  }
}

module network 'modules/network.bicep' = {
  name: 'network'
  scope: resourceGroup
  params: {
    name: 'vnet-${resourceToken}'
    location: location
    tags: tags
  }
}

module aiFoundry 'modules/ai-foundry.bicep' = {
  name: 'ai-foundry'
  scope: resourceGroup
  params: {
    name: 'aif-${resourceToken}'
    location: location
    tags: tags
    modelVersion: aiFoundryModelVersion
  }
}

module storageAccount 'modules/storage-account.bicep' = {
  name: 'storage-account'
  scope: resourceGroup
  params: {
    name: 'st${resourceToken}'
    location: location
    tags: tags
  }
}

module aiSearch 'modules/ai-search.bicep' = {
  name: 'ai-search'
  scope: resourceGroup
  params: {
    name: 'srch-${resourceToken}'
    location: location
    tags: tags
  }
}

module documentIntelligence 'modules/document-intelligence.bicep' = {
  name: 'document-intelligence'
  scope: resourceGroup
  params: {
    name: 'di-${resourceToken}'
    location: location
    tags: tags
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  scope: resourceGroup
  params: {
    name: 'psql-${resourceToken}'
    location: location
    tags: tags
    administratorPassword: postgresAdminPassword
  }
}

module containerAppsEnvironment 'modules/container-apps-environment.bicep' = {
  name: 'container-apps-environment'
  scope: resourceGroup
  params: {
    name: 'cae-${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    infrastructureSubnetId: network.outputs.infraSubnetId
  }
}

module deployerKeyVaultAccess 'modules/key-vault-rbac.bicep' = {
  name: 'deployer-key-vault-access'
  scope: resourceGroup
  params: {
    keyVaultName: keyVault.outputs.name
    principalId: principalId
  }
}

module appInsights 'modules/app-insights.bicep' = {
  name: 'app-insights'
  scope: resourceGroup
  params: {
    name: 'appi-${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    keyVaultName: keyVault.outputs.name
  }
  dependsOn: [
    deployerKeyVaultAccess
  ]
}

// Depends on deployerKeyVaultAccess (implicitly, via keyVaultName + the fact
// that both write secrets under RBAC authorization) so the deploying
// principal already has Key Vault Secrets Officer before either tries to
// write a secret value.
module redis 'modules/redis.bicep' = {
  name: 'redis'
  scope: resourceGroup
  params: {
    name: 'redis-${resourceToken}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
  dependsOn: [
    deployerKeyVaultAccess
  ]
}

module postgresPrivateEndpoint 'modules/private-endpoint.bicep' = {
  name: 'postgres-private-endpoint'
  scope: resourceGroup
  params: {
    name: 'pe-psql-${resourceToken}'
    location: location
    tags: tags
    vnetId: network.outputs.vnetId
    subnetId: network.outputs.privateEndpointSubnetId
    privateLinkServiceId: postgres.outputs.id
    groupId: 'postgresqlServer'
    privateDnsZoneName: 'privatelink.postgres.database.azure.com'
  }
}

module searchPrivateEndpoint 'modules/private-endpoint.bicep' = {
  name: 'search-private-endpoint'
  scope: resourceGroup
  params: {
    name: 'pe-srch-${resourceToken}'
    location: location
    tags: tags
    vnetId: network.outputs.vnetId
    subnetId: network.outputs.privateEndpointSubnetId
    privateLinkServiceId: aiSearch.outputs.id
    groupId: 'searchService'
    privateDnsZoneName: 'privatelink.search.windows.net'
  }
}

module aiFoundryPrivateEndpoint 'modules/private-endpoint.bicep' = {
  name: 'ai-foundry-private-endpoint'
  scope: resourceGroup
  params: {
    name: 'pe-aif-${resourceToken}'
    location: location
    tags: tags
    vnetId: network.outputs.vnetId
    subnetId: network.outputs.privateEndpointSubnetId
    privateLinkServiceId: aiFoundry.outputs.id
    groupId: 'account'
    privateDnsZoneName: 'privatelink.cognitiveservices.azure.com'
  }
}

module apiSecrets 'modules/key-vault-secrets.bicep' = {
  name: 'api-secrets'
  scope: resourceGroup
  params: {
    keyVaultName: keyVault.outputs.name
    databaseUrl: databaseUrl
    entraApiClientSecret: entraApiClientSecret
  }
  dependsOn: [
    deployerKeyVaultAccess
  ]
}

module api 'modules/container-app-api.bicep' = {
  name: 'api'
  scope: resourceGroup
  params: {
    name: 'ca-api-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
    containerAppsEnvironmentId: containerAppsEnvironment.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    keyVaultName: keyVault.outputs.name
    entraTenantId: entraTenantId
    entraApiClientId: entraApiClientId
    azureOpenAiEndpoint: aiFoundry.outputs.endpoint
    azureOpenAiDeployment: 'gpt-5-mini'
    azureOpenAiEmbeddingDeployment: 'text-embedding-3-small'
    aiFoundryAccountName: aiFoundry.outputs.name
    storageAccountName: storageAccount.outputs.name
    azureStorageAccountUrl: storageAccount.outputs.primaryBlobEndpoint
    azureSearchEndpoint: aiSearch.outputs.endpoint
    azureSearchIndexName: 'documents'
    searchServiceName: aiSearch.outputs.name
  }
  dependsOn: [
    apiSecrets
    redis
    appInsights
  ]
}

module documentProcessorFunction 'modules/function-app.bicep' = {
  name: 'document-processor-function'
  scope: resourceGroup
  params: {
    name: 'func-docs-${resourceToken}'
    location: location
    tags: tags
    storageAccountName: storageAccount.outputs.name
    databaseUrl: databaseUrl
    azureOpenAiEndpoint: aiFoundry.outputs.endpoint
    azureOpenAiDeployment: 'gpt-5-mini'
    azureOpenAiEmbeddingDeployment: 'text-embedding-3-small'
    azureSearchEndpoint: aiSearch.outputs.endpoint
    azureSearchIndexName: 'documents'
    documentIntelligenceEndpoint: documentIntelligence.outputs.endpoint
    aiFoundryAccountName: aiFoundry.outputs.name
    documentIntelligenceAccountName: documentIntelligence.outputs.name
    searchServiceName: aiSearch.outputs.name
    keyVaultName: keyVault.outputs.name
    functionIntegrationSubnetId: network.outputs.functionIntegrationSubnetId
  }
  dependsOn: [
    appInsights
  ]
}

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_KEY_VAULT_NAME string = keyVault.outputs.name
output AZURE_KEY_VAULT_ENDPOINT string = keyVault.outputs.endpoint
output SERVICE_API_URI string = api.outputs.uri
output AZURE_RESOURCE_GROUP string = resourceGroup.name
output DOCUMENT_PROCESSOR_FUNCTION_NAME string = documentProcessorFunction.outputs.name
output AZURE_SEARCH_ENDPOINT string = aiSearch.outputs.endpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storageAccount.outputs.name
