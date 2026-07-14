param name string
param location string
param tags object
param containerAppsEnvironmentId string
param containerRegistryLoginServer string
param keyVaultName string
param entraTenantId string
param entraApiClientId string
param azureOpenAiEndpoint string
param azureOpenAiDeployment string
param aiFoundryAccountName string

@description('Placeholder image used on first deploy; azd/CI replaces this with the built image on subsequent deploys.')
param apiImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var keyVaultSecretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
var cognitiveServicesOpenAiUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: split(containerRegistryLoginServer, '.')[0]
}

resource aiFoundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiFoundryAccountName
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: containerRegistryLoginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/database-url'
          identity: 'system'
        }
        {
          name: 'entra-api-client-secret'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/entra-api-client-secret'
          identity: 'system'
        }
        {
          name: 'redis-url'
          keyVaultUrl: '${keyVault.properties.vaultUri}secrets/redis-url'
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'ENVIRONMENT', value: 'production' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
            { name: 'ENTRA_API_CLIENT_SECRET', secretRef: 'entra-api-client-secret' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
      }
    }
  }
}

// Known Azure race: on the very first deploy, the Container App's system
// identity doesn't have Key Vault/ACR access yet when this resource's own
// PUT tries to resolve secretRefs/registry auth. If the first `azd up`
// fails on secret resolution, re-run `azd deploy` — the role assignments
// below will already exist and the retry succeeds.
resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, containerApp.id, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVaultSecretsUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, containerApp.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource cognitiveServicesOpenAiUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiFoundryAccount.id, containerApp.id, cognitiveServicesOpenAiUserRoleId)
  scope: aiFoundryAccount
  properties: {
    roleDefinitionId: cognitiveServicesOpenAiUserRoleId
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output uri string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output name string = containerApp.name
output principalId string = containerApp.identity.principalId
