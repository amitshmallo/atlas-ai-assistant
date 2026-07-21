param name string
param location string
param tags object

@secure()
param administratorPassword string

param administratorLogin string = 'atlasadmin'

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    // Phase 10: no public network access and no firewall rules at all —
    // reachable only via the private endpoint main.bicep sets up on the
    // VNet's private-endpoints subnet.
    network: {
      publicNetworkAccess: 'Disabled'
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'atlas'
}

output fqdn string = postgres.properties.fullyQualifiedDomainName
output name string = postgres.name
output id string = postgres.id
