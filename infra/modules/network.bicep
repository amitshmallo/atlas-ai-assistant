param name string
param location string
param tags object

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
    subnets: [
      {
        // Container Apps environment VNet integration — delegated per
        // Microsoft's requirement, sized /23 since workload-profile
        // environments need more addresses than the /27 minimum for
        // Consumption-only environments.
        name: 'infra'
        properties: {
          addressPrefix: '10.0.0.0/23'
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.0.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        // Regional VNet integration for the Function App's *outbound*
        // calls (reaching private Postgres/Search/AI Foundry) — separate
        // from and unrelated to the blob-trigger polling limitation that's
        // why Storage itself stays public (see storage-account.bicep).
        // Needs its own subnet, delegated differently from the Container
        // Apps one, and must be empty (no other resources in it).
        name: 'function-integration'
        properties: {
          addressPrefix: '10.0.3.0/24'
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output infraSubnetId string = vnet.properties.subnets[0].id
output privateEndpointSubnetId string = vnet.properties.subnets[1].id
output functionIntegrationSubnetId string = vnet.properties.subnets[2].id
