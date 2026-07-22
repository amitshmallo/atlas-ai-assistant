param name string
param location string
param tags object
param storageAccountName string
param databaseUrl string
param azureOpenAiEndpoint string
param azureOpenAiDeployment string
param azureOpenAiEmbeddingDeployment string
param azureSearchEndpoint string
param azureSearchIndexName string
param documentIntelligenceEndpoint string
param aiFoundryAccountName string
param documentIntelligenceAccountName string
param searchServiceName string
param keyVaultName string
param functionIntegrationSubnetId string

var storageBlobDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var storageBlobDataOwnerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b')
var searchIndexDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
var cognitiveServicesUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
var cognitiveServicesOpenAiUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
var keyVaultSecretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource storageBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  name: 'default'
  parent: storageAccount
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: 'deploymentpackage'
  parent: storageBlobService
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: searchServiceName
}

resource documentIntelligenceAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: documentIntelligenceAccountName
}

resource aiFoundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiFoundryAccountName
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${name}-plan'
  location: location
  tags: tags
  // Flex Consumption draws from a separate quota pool than classic
  // Dynamic/Basic App Service plans — this subscription has zero quota for
  // those (confirmed in two different regions), but FC1 isn't subject to
  // the same restriction.
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: name
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: functionIntegrationSubnetId
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storageAccount.properties.primaryEndpoints.blob}${deploymentContainer.name}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.12'
      }
    }
    siteConfig: {
      // Outbound calls (reaching private Postgres/Search/AI Foundry over
      // VNet peering) route through functionIntegrationSubnetId regardless
      // of this; keeping route-all off means only traffic to the peered
      // VNets' address spaces goes through it, so calls to public endpoints
      // (Document Intelligence, Azure OpenAI's own storage, etc.) don't
      // take an unnecessary detour.
      vnetRouteAllEnabled: false
      appSettings: [
        {
          // Flex Consumption uses identity-based storage settings, not the
          // classic AzureWebJobsStorage connection string.
          name: 'AzureWebJobsStorage__accountName'
          value: storageAccount.name
        }
        { name: 'DATABASE_URL', value: databaseUrl }
        { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
        { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
        { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: azureOpenAiEmbeddingDeployment }
        { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
        { name: 'AZURE_SEARCH_INDEX_NAME', value: azureSearchIndexName }
        { name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT', value: documentIntelligenceEndpoint }
        {
          // Turns on Azure Functions' built-in Application Insights
          // integration (host.json already has the logging config for it)
          // — no code changes needed in function_app.py for this. Resolved
          // by the platform at runtime via the role assignment below, not
          // at ARM deployment time — same known first-deploy race as the
          // API Container App's Key Vault secrets (see container-app-api.bicep).
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/appinsights-connection-string/)'
        }
      ]
    }
  }
}

// No API keys anywhere above — the Function authenticates to Storage,
// Search, Document Intelligence, and Azure OpenAI purely via these role
// assignments on its own managed identity, same pattern as the API
// Container App.
resource storageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageBlobDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: storageBlobDataContributorRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Flex Consumption's identity-based deployment storage needs Owner
// specifically (Contributor above isn't sufficient for it) — scoped to just
// the deployment container, not the whole storage account.
resource deploymentStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(deploymentContainer.id, functionApp.id, storageBlobDataOwnerRoleId)
  scope: deploymentContainer
  properties: {
    roleDefinitionId: storageBlobDataOwnerRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource searchRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, functionApp.id, searchIndexDataContributorRoleId)
  scope: searchService
  properties: {
    roleDefinitionId: searchIndexDataContributorRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource documentIntelligenceRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentIntelligenceAccount.id, functionApp.id, cognitiveServicesUserRoleId)
  scope: documentIntelligenceAccount
  properties: {
    roleDefinitionId: cognitiveServicesUserRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource openAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiFoundryAccount.id, functionApp.id, cognitiveServicesOpenAiUserRoleId)
  scope: aiFoundryAccount
  properties: {
    roleDefinitionId: cognitiveServicesOpenAiUserRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVaultSecretsUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionApp.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output name string = functionApp.name
output principalId string = functionApp.identity.principalId
