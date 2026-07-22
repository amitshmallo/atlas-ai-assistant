@description('A small VNet in the document-processor Function App region — separate from the main VNet because this subscription has no Microsoft.Web/serverfarms compute quota in the primary region, so the Function has to live elsewhere. Peered with the main VNet (see main.bicep) so it can still reach Postgres/AI Search/AI Foundry over their private endpoints instead of the public internet.')
param name string
param location string
param tags object

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.1.0.0/16']
    }
    subnets: [
      {
        // Flex Consumption's VNet integration is built on the same
        // underlying infra as Container Apps — it requires this delegation,
        // not Microsoft.Web/serverFarms (which is what classic Dynamic/
        // Basic plans need).
        name: 'function-integration'
        properties: {
          addressPrefix: '10.1.0.0/24'
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
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output functionIntegrationSubnetId string = vnet.properties.subnets[0].id
