# Configuration Patterns & Best Practices

This guide provides recommended configuration patterns for common SAP OData extraction scenarios.

## Understanding Load Type vs Fetch Type

### Load Type (Storage)
Controls **how data is written** to Keboola Storage:
- **Full Load**: Replaces entire table on each run (truncate & insert)
- **Incremental Load**: Appends data with upsert based on primary key

### Fetch Type (OData)
Controls **how data is extracted** from SAP OData API:
- **Full Fetch**: Extracts all records every time
- **Incremental Fetch**: Extracts only new/changed records using timestamp filter

---

## Recommended Patterns

### Pattern 1: Simple Full Extraction
**Best for**: Small datasets (<100K records), dimension tables, reference data

```json
{
  "load_type": "full",
  "fetch_type": "full",
  "primary_key": []
}
```

**Characteristics:**
- ✅ Simple and reliable
- ✅ Always up-to-date
- ✅ No risk of missing data
- ❌ Slower for large datasets
- ❌ Higher API costs

**Use cases:**
- Product catalogs (10K products)
- Employee master data
- Cost centers, GL accounts
- Configuration tables

---

### Pattern 2: Efficient Incremental (Recommended for Large Tables)
**Best for**: Large fact tables, transactional data with timestamp fields

```json
{
  "load_type": "incremental",
  "fetch_type": "incremental",
  "incremental_field": "LastChangedAt",
  "primary_key": ["SalesOrderID", "ItemNumber"]
}
```

**Characteristics:**
- ✅ Very fast extraction
- ✅ Low API costs
- ✅ Historical data preserved
- ✅ Scales to millions of records
- ⚠️ Requires reliable timestamp field
- ⚠️ Needs proper primary key

**Use cases:**
- Sales orders (millions of records)
- Financial documents
- Time sheets, work orders
- IoT sensor data

**Requirements:**
1. Entity must have timestamp field that updates on changes
2. Timestamp field must be indexed in SAP
3. Primary key must uniquely identify records

---

### Pattern 3: Change Data Capture (CDC)
**Best for**: Tracking latest state only, no historical records needed

```json
{
  "load_type": "full",
  "fetch_type": "incremental",
  "incremental_field": "ModifiedOn",
  "primary_key": []
}
```

**Characteristics:**
- ✅ Fast extraction (only changes)
- ✅ Lower API costs than full fetch
- ✅ Simple table structure
- ❌ No historical records
- ❌ Table replaced on each run

**Use cases:**
- Material stock levels (current state only)
- Customer status (active/inactive)
- Price lists (latest prices only)
- Configuration that changes occasionally

**How it works:**
1. First run: Extracts all records
2. Subsequent runs: Extracts only changed records (via $filter)
3. Each run replaces the entire Keboola table

---

### Pattern 4: Historical Append (Without Updates)
**Best for**: Immutable event logs, audit trails

```json
{
  "load_type": "incremental",
  "fetch_type": "incremental",
  "incremental_field": "CreatedAt",
  "primary_key": []
}
```

**Characteristics:**
- ✅ Fast extraction
- ✅ Complete event history
- ✅ No deduplication needed
- ⚠️ Records never update (append-only)
- ⚠️ Table grows continuously

**Use cases:**
- System logs
- Audit trails
- Webhooks, notifications
- Event streams

**Important:**
- Use `CreatedAt` field (not `ModifiedAt`)
- Records should never be modified after creation
- No primary key = all records appended

---

### Pattern 5: Daily Snapshots
**Best for**: Point-in-time analysis, slowly changing dimensions

```json
{
  "load_type": "incremental",
  "fetch_type": "full",
  "primary_key": ["RecordID", "SnapshotDate"]
}
```

**Characteristics:**
- ✅ Complete daily snapshots
- ✅ Track changes over time
- ✅ No missed updates
- ❌ Higher API costs
- ❌ Larger storage requirements

**Use cases:**
- Inventory levels (daily snapshot)
- Employee headcount tracking
- Budget vs actual analysis
- SCD Type 2 dimensions

**Implementation:**
- Add current date to each record
- Include date in primary key
- Enables time-series analysis

---

## Field Selection Strategies

### Strategy 1: Minimal Fields (Performance)
```json
{
  "select_fields": ["OrderID", "CustomerID", "Amount", "Status", "CreatedAt"],
  "expand_properties": []
}
```

**Best for**: Large extractions, API cost optimization

### Strategy 2: Full Entity (Completeness)
```json
{
  "select_fields": [],
  "expand_properties": []
}
```

**Best for**: Small tables, unknown requirements

### Strategy 3: With Related Data
```json
{
  "select_fields": ["OrderID", "CustomerID", "Amount"],
  "expand_properties": ["Customer", "Items"]
}
```

**Best for**: Denormalized reporting, avoiding multiple API calls

---

## Filter Examples

### Active Records Only
```
Status eq 'Active'
```

### Recent Records
```
CreatedAt gt 2024-01-01T00:00:00Z
```

### Complex Business Logic
```
(Status eq 'Open' or Status eq 'InProgress') and Priority eq 'High' and AssignedTo ne null
```

### Date Range
```
OrderDate ge 2024-01-01T00:00:00Z and OrderDate le 2024-12-31T23:59:59Z
```

---

## Performance Optimization

### For Large Tables (>1M records)
1. Use **Incremental Fetch + Incremental Load**
2. Reduce page_size to 500-1000
3. Select only required fields
4. Add filter to reduce dataset
5. Ensure timestamp field is indexed in SAP

### For Wide Tables (>50 columns)
1. Use `select_fields` to limit columns
2. Reduce page_size to 500
3. Avoid expand_properties
4. Consider splitting into multiple extractions

### For Complex Relationships
1. Use separate rows for parent and child entities
2. Join in Keboola Transformations
3. Avoid deeply nested expands (max 2 levels)

---

## Common Mistakes

### ❌ Wrong: Incremental Load without Primary Key
```json
{
  "load_type": "incremental",
  "primary_key": []
}
```
**Problem**: Duplicate records on every run

### ❌ Wrong: Incremental Fetch without Timestamp Field
```json
{
  "fetch_type": "incremental",
  "incremental_field": ""
}
```
**Problem**: Can't filter for new records

### ❌ Wrong: Using CreatedAt for Updates
```json
{
  "fetch_type": "incremental",
  "incremental_field": "CreatedAt"
}
```
**Problem**: Misses record updates (only gets new records)

### ✅ Correct: Full Configuration
```json
{
  "load_type": "incremental",
  "fetch_type": "incremental",
  "incremental_field": "LastChangedAt",
  "primary_key": ["RecordID"]
}
```

---

## Troubleshooting

### Missing Records
**Symptoms**: Some records don't appear in Keboola
**Solutions**:
1. Check timestamp field updates correctly in SAP
2. Verify $filter syntax with Validate Filter button
3. Temporarily switch to full fetch to verify
4. Check SAP server timezone settings

### Duplicate Records
**Symptoms**: Same record appears multiple times
**Solutions**:
1. Add primary_key for incremental load
2. Ensure primary key is truly unique
3. Check for composite keys (multiple fields)

### Slow Extraction
**Symptoms**: Extraction takes too long
**Solutions**:
1. Reduce page_size to 500-1000
2. Add select_fields to limit columns
3. Add filter to reduce dataset
4. Switch to incremental fetch
5. Check SAP server indexes

### High API Costs
**Symptoms**: API quota exceeded
**Solutions**:
1. Switch to incremental fetch
2. Increase incremental_field frequency (hourly → daily)
3. Add filters to reduce data volume
4. Select fewer fields
5. Schedule extractions less frequently

---

## Migration Guide

### From Full to Incremental

1. **Identify timestamp field**
   ```sql
   -- Check SAP entity metadata for timestamp fields
   -- Common names: LastChangedAt, ModifiedOn, SystemModstamp
   ```

2. **Test incremental fetch**
   ```json
   {
     "fetch_type": "incremental",
     "incremental_field": "LastChangedAt",
     "max_records": 1000
   }
   ```

3. **Verify primary key**
   - Ensure uniqueness
   - Test with sample data

4. **Switch load type**
   ```json
   {
     "load_type": "incremental",
     "fetch_type": "incremental",
     "incremental_field": "LastChangedAt",
     "primary_key": ["RecordID"]
   }
   ```

5. **Monitor first runs**
   - Check for duplicates
   - Verify all changes captured
   - Monitor performance

---

## SAP-Specific Recommendations

### S/4HANA Cloud
- Use OData V4 services where available
- Prefer CDS views over classic BAPIs
- Enable $expand for related data

### SAP Business ByDesign
- Use OData V2 services
- Add APIKey authentication
- Set timeout to 120s+ for reports

### SAP SuccessFactors
- Use compound entity sets (Employment, PerPerson)
- Always include effectiveStartDate in primary key
- Filter by lastModifiedDateTime

### SAP Ariba
- Use basic authentication
- Add realm parameter to base URL
- Filter by TimeUpdated for incremental

---

## Summary Table

| Use Case | Load Type | Fetch Type | Primary Key | Incremental Field |
|----------|-----------|------------|-------------|-------------------|
| Small reference tables | Full | Full | ❌ | ❌ |
| Large transactional data | Incremental | Incremental | ✅ | ✅ |
| Latest state only | Full | Incremental | ❌ | ✅ |
| Event logs (append-only) | Incremental | Incremental | ❌ | ✅ |
| Daily snapshots | Incremental | Full | ✅ (with date) | ❌ |

---

## Additional Resources

- [SAP API Business Hub](https://api.sap.com/)
- [OData Documentation](https://www.odata.org/documentation/)
- [Keboola Incremental Loading](https://help.keboola.com/storage/tables/#incremental-loading)
- [SAP Gateway Development](https://help.sap.com/docs/SAP_NETWEAVER_750/68bf513362174d54b58cddec28794093/e6f7c2fad4bd453eb5ee75b5d2685885.html)
