@description('Bidirectional peering between the main VNet and the document-processor Function App\'s VNet, which lives in a different region because this subscription has no App Service compute quota in the primary region. Lets the Function reach Postgres/AI Search/AI Foundry over their private endpoints instead of the public internet.')
param mainVnetName string
param mainVnetId string
param functionVnetName string
param functionVnetId string

resource mainVnet 'Microsoft.Network/virtualNetworks@2024-01-01' existing = {
  name: mainVnetName
}

resource functionVnet 'Microsoft.Network/virtualNetworks@2024-01-01' existing = {
  name: functionVnetName
}

resource mainToFunctionPeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-01-01' = {
  parent: mainVnet
  name: 'to-function-network'
  properties: {
    remoteVirtualNetwork: {
      id: functionVnetId
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: false
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

resource functionToMainPeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-01-01' = {
  parent: functionVnet
  name: 'to-main-network'
  properties: {
    remoteVirtualNetwork: {
      id: mainVnetId
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: false
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}
