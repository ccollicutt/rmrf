# Protection Levels Configuration

This directory contains YAML configuration files for rmrf protection levels.

## Default Protection Levels

| Level               | Environment | Description                                 | Max Files | Max Size | Retention |
| ------------------- | ----------- | ------------------------------------------- | --------- | -------- | --------- |
| **safe-local**      | dev         | Minimal restrictions; rollback optional     | None      | None     | 3 days    |
| **controlled-team** | staging     | Rollback required; one confirmation         | 10,000    | 10 GB    | 7 days    |
| **guarded-ops**     | ops         | Approval workflow; audit required           | 5,000     | 5 GB     | 14 days   |
| **critical-system** | prod        | Dual confirmation; backup + audit required  | 1,000     | 1 GB     | 30 days   |
| **simulation-only** | twin        | Dry-run only; no actual deletion            | None      | None     | 7 days    |

## Custom Protection Levels

To create a custom protection level, add a new YAML file to this directory or to `/etc/rmrf/protection_levels.d/`.

### YAML Schema

```yaml
# Required fields
name: my-custom-level              # Unique identifier (lowercase with hyphens)
description: "Human-readable desc" # What this level does

# Optional fields
default_environment: custom        # Environment this level applies to
max_files: 5000                    # Maximum files allowed in plan
max_bytes: 5368709120              # Maximum total bytes (5 GB example)
require_backup: true               # Whether backup is required
require_audit: true                # Whether audit events are required
require_confirmation: true         # Whether human confirmation is required
retention_days: 14                 # How long to retain backups
allow_simulation_only: false       # If true, only dry-run mode allowed
```

### Example Custom Level

```yaml
name: audit-strict
description: "High audit retention mode"
default_environment: audit
max_files: 1000
max_bytes: 1073741824  # 1 GB
require_backup: true
require_audit: true
require_confirmation: true
retention_days: 90     # 90 days for compliance
allow_simulation_only: false
```

## Loading Order

1. Built-in defaults are loaded first
2. Files from this directory (`config/protection_levels/`) are loaded next
3. Files from `/etc/rmrf/protection_levels.d/` are loaded last (overriding earlier definitions)

## Field Details

### `max_files` and `max_bytes`
- If `null` or omitted, no limit is enforced
- Plans exceeding these limits will be flagged as high risk

### `require_backup`
- If `true`, files must be backed up before deletion
- Backup failures will abort the operation (depending on protection level)

### `require_audit`
- If `true`, audit events must be successfully emitted
- Audit failures in high protection levels will abort the operation

### `require_confirmation`
- If `true`, user must provide confirmation phrase before execution
- Critical-System uses dual confirmation

### `retention_days`
- How long backups are retained before cleanup
- Cleanup is performed by scheduled retention policy enforcement

### `allow_simulation_only`
- If `true`, only dry-run mode is permitted
- Attempts to perform actual deletion will be rejected

## Validation

All protection levels are validated on load:
- Names must be lowercase with hyphens
- Numeric values must be non-negative
- Required fields must be present

Invalid YAML files will be logged but will not prevent loading other files.
