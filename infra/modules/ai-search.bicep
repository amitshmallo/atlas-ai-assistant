param name string
param location string
param tags object

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  // Basic, not Free: Private Endpoint support requires Basic tier or above
  // — Free (shared/multi-tenant) doesn't support VNet features at all. If
  // you're just testing locally without deploying, the Free tier used in
  // the manual portal setup (README "Provision Azure AI Search") is fine
  // and costs nothing; this Bicep path is the "azd up", fully-networked
  // deployment, where Basic's ~$75/mo is the real cost of Phase 10's
  // private networking requirement for this specific resource.
  sku: {
    name: 'basic'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    publicNetworkAccess: 'disabled'
  }
}

output endpoint string = 'https://${searchService.name}.search.windows.net'
output name string = searchService.name
output id string = searchService.id
