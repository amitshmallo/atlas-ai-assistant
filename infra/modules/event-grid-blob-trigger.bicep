@description('Routes Microsoft.Storage.BlobCreated events from the documents container to the document-processor Function — Flex Consumption only supports Event Grid as a blob trigger source, not the classic polling-based connection string trigger.')
param storageAccountName string
param storageAccountId string
param functionAppName string
param functionAppId string
param location string
param tags object

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' existing = {
  name: functionAppName
}

resource systemTopic 'Microsoft.EventGrid/systemTopics@2023-12-15-preview' = {
  name: '${storageAccountName}-evgt'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    source: storageAccountId
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

resource eventSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2023-12-15-preview' = {
  parent: systemTopic
  name: 'documents-blob-created'
  properties: {
    destination: {
      endpointType: 'AzureFunction'
      properties: {
        resourceId: '${functionAppId}/functions/process_uploaded_document'
        maxEventsPerBatch: 1
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
      ]
      subjectBeginsWith: '/blobServices/default/containers/documents/'
    }
    eventDeliverySchema: 'EventGridSchema'
  }
  dependsOn: [
    functionApp
  ]
}
