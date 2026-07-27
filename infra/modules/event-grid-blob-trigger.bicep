@description('Routes Microsoft.Storage.BlobCreated events to the document-processor Function. A blob trigger configured with source=EventGrid still requires the Event Grid subscription to be wired manually — there is no "AzureFunction" destination support for it (confirmed: "Azure Event Grid supports EventGrid Trigger type only"). The correct destination is a WebHook pointing at the function host\'s own blob-extension endpoint (visible in its own startup log as "registered http endpoint"), authenticated with its system key.')
param storageAccountId string
param functionAppName string
param location string
param tags object

resource functionApp 'Microsoft.Web/sites@2023-12-01' existing = {
  name: functionAppName
}

var systemKeys = listkeys('${functionApp.id}/host/default', '2023-12-01')

resource systemTopic 'Microsoft.EventGrid/systemTopics@2023-12-15-preview' = {
  name: '${functionAppName}-evgt'
  location: location
  tags: tags
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
      endpointType: 'WebHook'
      properties: {
        endpointUrl: 'https://${functionApp.properties.defaultHostName}/runtime/webhooks/blobs?functionName=Host.Functions.process_uploaded_document&code=${systemKeys.systemKeys.blobs_extension}'
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
}
