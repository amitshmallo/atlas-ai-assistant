param name string
param location string
param tags object

@description('Model deployment name the AZURE_OPENAI_DEPLOYMENT setting points at')
param deploymentName string = 'gpt-5-mini'

@description('Underlying model name/version to deploy — verify the current version string in the AI Foundry portal or `az cognitiveservices account list-models` before deploying, model versions get retired/replaced over time')
param modelName string = 'gpt-5-mini'
param modelVersion string

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: deploymentName
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

output endpoint string = account.properties.endpoint
output name string = account.name
output id string = account.id
