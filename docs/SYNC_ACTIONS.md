# Sync Actions

Sync actions are interactive UI operations that run when users click buttons (e.g., "Load Entity Sets", "Load Available Services") in the Keboola component configuration form. They provide dynamic dropdowns, validation, and data previews.

## How Sync Actions Work

### Keboola `@sync_action` Decorator

Each sync action is a method decorated with `@sync_action("actionName")` from `keboola.component.base`. The decorator handles the execution lifecycle:

| Outcome | Mechanism | Exit Code | UI Behavior |
|---------|-----------|-----------|-------------|
| **Success** | Method returns a value (list/dict) | 0 | Value written to stdout as JSON; UI populates dropdown or shows result |
| **Error** | Unhandled exception propagates | 1 | Exception message written to stderr; UI shows red error toast notification |

**Key principle:** To show an error in the UI, raise an exception (typically `UserException`). To populate a dropdown, return a list of `{"value": ..., "label": ...}` items.

### Return Value Formats

**Dropdown items** (used by `loadServices`, `loadEntities`, `loadFields`, etc.):
```python
[
    {"value": "actual_value", "label": "Human-readable label"},
    {"value": "another_value", "label": "Another label"},
]
```

**Guidance items** (when config is incomplete, guide the user):
```python
[
    {"value": "", "label": "Warning message guiding the user"}
]
```

> **Note:** Items with `"value": ""` are filtered out by the UI dropdown. They serve as a no-op return that doesn't populate the dropdown but also doesn't trigger an error.

**Status responses** (used by `testConnection`, `validateFilter`, `previewData`):
```python
{"status": "success", "message": "Human-readable message"}
```

## Error Handling Strategy

### Three Categories of Responses

| Category | When | How | UI Result |
|----------|------|-----|-----------|
| **API/HTTP error** | 401, 403, 404, timeout, connection refused | Raise `UserException` | Red error toast with message |
| **Empty result** | Valid API response but no data found | Raise `UserException` (for catalog) or return guidance item (for metadata) | Error toast or empty dropdown |
| **Missing config** | Required field not yet filled by user | Return guidance item `{"value": "", "label": "..."}` | Empty dropdown (no error) |

### Why the Distinction Matters

- **Missing config** is normal during form filling -- the user hasn't finished configuring yet. Showing an error toast would be disruptive.
- **API errors** indicate a real problem (wrong credentials, unreachable server). The user needs to see a clear error message.
- **Empty results** from catalog endpoints are suspicious (catalog should have services), but empty metadata entity sets can be a valid API response for misconfigured service paths.

## Sync Action Reference

### `testConnection`

**Action name:** `testConnection`
**Schema location:** `configSchema.json` (root config)
**UI element:** "Test Connection" button

**Behavior:**
1. Validates `base_url` is configured
2. Sends HTTP GET to `base_url` with auth headers
3. If `catalog_path` is set, also tests catalog URL
4. Returns `{"status": "success/error/warning", "message": "..."}`

**Error handling:** Catches all exceptions internally and returns status dict (never raises). This is because `testConnection` uses the `format: "test-connection"` UI widget which expects a status object, not a dropdown.

---

### `loadServices`

**Action name:** `loadServices`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Load Available Services" button next to Service Path dropdown

**Behavior:**
1. If `base_url` missing -> returns guidance item
2. If `catalog_path` missing -> returns guidance item
3. Sends pre-flight HTTP GET to catalog URL to detect HTTP errors early
4. Calls `client.list_catalog_services()` to parse the catalog response (ATOM XML or JSON)
5. If no services found -> raises `UserException`
6. Returns list of `{"value": "service_path", "label": "Title - Description"}`

**Error handling:**
- Missing config -> guidance item (exit 0, empty dropdown)
- HTTP 401/403/404/500, connection error, timeout -> `UserException` (exit 1, error toast)
- Empty catalog -> `UserException` (exit 1, error toast)
- Successful with services -> dropdown populated

**Important implementation detail:** The `list_catalog_services()` method in `async_base_client.py` has a broad `except Exception` that catches parsing errors. To prevent it from swallowing HTTP/auth errors, `except UserException: raise` is placed before the broad except:

```python
except UserException:
    raise  # HTTP/auth errors must propagate to the caller so the UI sees them
except Exception as e:
    logging.warning(f"Failed to parse catalog response: {e}")
    return []
```

---

### `loadEntities`

**Action name:** `loadEntities`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Load Entity Sets" button next to Entity Set dropdown (also has `autoload: true`)

**Behavior:**
1. If `base_url` missing -> returns guidance item
2. If `service_path` missing -> returns guidance item
3. Fetches `$metadata` from `{base_url}/{service_path}/$metadata`
4. Parses entity sets from EDMX metadata
5. If no entity sets found -> raises `UserException`
6. Returns list of `{"value": "EntitySetName", "label": "EntitySetName"}`

**Error handling:**
- Missing config -> guidance item (exit 0, empty dropdown)
- HTTP errors (401, connection failed, etc.) -> `UserException` propagates from httpx client (exit 1, error toast)
- Empty entity sets -> `UserException` (exit 1, error toast)

---

### `loadFields`

**Action name:** `loadFields`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Load Fields" button next to Select Fields multi-select

**Behavior:**
1. If `entity_set` missing -> returns guidance item
2. Fetches metadata and lists all properties of the entity set
3. Enriches labels with EDM type, KEY marker, SAP annotations (filterable, label, quickinfo)
4. Returns list of `{"value": "FieldName", "label": "FieldName (SAP Label) - Edm.String [KEY, filterable]"}`

**Error handling:**
- Missing entity set -> guidance item
- HTTP/metadata errors -> `UserException` propagates from client
- Empty fields -> returns empty list `[]`

---

### `loadPossiblePrimaryKeys`

**Action name:** `loadPossiblePrimaryKeys`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Load Primary Keys" button next to Primary Key multi-select

**Behavior:**
1. If `entity_set` missing -> returns guidance item
2. Fetches metadata and extracts key properties of the entity set
3. Returns list of `{"value": "KeyField", "label": "KeyField (Key)"}`

**Error handling:**
- Missing entity set -> guidance item
- Entity not found in metadata -> `UserException`
- HTTP errors -> `UserException` propagates from client

---

### `loadIncrementalFields`

**Action name:** `loadIncrementalFields`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Load Incremental Fields" button next to Incremental Field dropdown

**Behavior:**
1. If `entity_set` missing -> returns guidance item
2. Fetches all fields and scores them by suitability for incremental fetching:
   - +10 points for datetime types (`Edm.DateTime`, `Edm.DateTimeOffset`, `Edm.Date`)
   - +5 points for name patterns (`lastchanged`, `modifiedat`, `updatedat`, etc.)
3. Returns candidates sorted by score (best first)

**Error handling:**
- Missing entity set -> guidance item
- HTTP errors -> `UserException` propagates from client
- No datetime fields found -> returns empty list `[]`

---

### `loadNavigationProperties`

**Action name:** `loadNavigationProperties`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Load Navigation Properties" button next to Expand Properties multi-select

**Behavior:**
1. If `entity_set` missing -> returns guidance item
2. Fetches metadata and extracts navigation properties
3. Returns list of `{"value": "NavPropName", "label": "NavPropName -> TargetEntity"}`

**Error handling:**
- Missing entity set -> guidance item
- Entity not found in metadata -> `UserException`
- HTTP errors -> `UserException` propagates from client

---

### `previewData`

**Action name:** `previewData`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Preview Data (10 records)" button

**Behavior:**
1. If `entity_set` missing -> raises `UserException`
2. Fetches first 10 records with configured select/filter/expand options
3. Formats data as markdown table
4. Returns `{"status": "success", "message": "Preview table...", "data": [...]}`

**Error handling:**
- Missing entity set -> `UserException` (error toast)
- HTTP/query errors -> `UserException` propagates from client

---

### `validateFilter`

**Action name:** `validateFilter`
**Schema location:** `configRowSchema.json` (row config)
**UI element:** "Validate Filter" button

**Behavior:**
1. If `entity_set` missing -> raises `UserException`
2. If no filter expression -> returns success
3. Executes filter with `$top=1` to validate syntax
4. Returns `{"status": "success", "message": "Filter expression is valid"}`

**Error handling:**
- Missing entity set -> `UserException`
- Invalid filter syntax -> OData server returns error, propagated as `UserException`

---

### `loadMetadataSummary`

**Action name:** `loadMetadataSummary`
**Schema location:** Not in UI schema (internal/debug action)

**Behavior:**
1. Fetches full metadata
2. Returns summary with OData version, entity count, and entity details

**Error handling:**
- HTTP errors -> `UserException` propagates from client

## Configuration Context

Sync actions receive configuration from **both** the root config and the row config merged together:

| Parameter | Source | Used by |
|-----------|--------|---------|
| `base_url` | Root config (`configSchema`) | All actions |
| `catalog_path` | Root config (`configSchema`) | `loadServices` |
| `authentication.*` | Root config (`configSchema`) | All actions (via `_build_auth_handler`) |
| `service_path` | Row config (`configRowSchema`) | `loadEntities`, `loadFields`, etc. |
| `entity_set` | Row config (`configRowSchema`) | `loadFields`, `loadPrimaryKeys`, etc. |
| `odata_version` | Row config (`configRowSchema`) | All actions (via `_detect_or_get_version`) |

## UI Schema Mapping

The sync actions are wired to UI elements via `options.async` in the JSON schema:

```json
{
  "type": "string",
  "format": "select",
  "enum": [],
  "options": {
    "creatable": true,
    "async": {
      "label": "Load Entity Sets",
      "action": "loadEntities",
      "autoload": true,
      "cache": true
    }
  }
}
```

- `format: "select"` + `enum: []` renders a dropdown with a load button
- `options.creatable: true` allows manual input alongside loaded options
- `options.async.action` maps to the `@sync_action("actionName")` decorator
- `options.async.autoload: true` triggers the action automatically on page load
- `options.async.cache: true` caches results to avoid repeated API calls
