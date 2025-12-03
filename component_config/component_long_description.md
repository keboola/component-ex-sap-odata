Generic extractor for SAP OData services supporting both OData V2 and V4 protocols.

## Features

- **Universal SAP OData connector** - supports any SAP OData service (S/4HANA, BW, CRM, SuccessFactors, etc.)
- **OData V2 and V4 support** - automatic version detection or explicit selection
- **Multiple authentication methods** - Basic authentication and OAuth 2.0
- **Full data extraction** - filtering, column selection, navigation property expansion
- **Incremental sync** - delta synchronization using state file
- **Dynamic UI** - entity sets and fields loaded from $metadata

## Configuration

### Authentication

The extractor supports two authentication methods:

1. **Basic Authentication** - Username and password
2. **OAuth 2.0** - Via Keboola OAuth Broker

### Entity Configuration

For each entity you want to extract, configure:

- **Entity Set** - Select from available entity sets
- **Select Fields** - Choose specific fields to extract
- **Filter Expression** - OData $filter syntax
- **Expand Properties** - Include related entities
- **Sync Type** - Full or incremental sync
- **Primary Key** - Fields for deduplication

## Supported OData Operations

- `$select` - Column selection
- `$filter` - Data filtering
- `$expand` - Navigation property expansion
- `$orderby` - Sorting
- `$top/$skip` - Pagination
- `$count` - Record counting
