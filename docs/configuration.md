# Configuration Guide

## Environment Detection

rmrf automatically detects your environment from:
1. `/etc/rmrf.env` - System-wide environment configuration
2. `$RM_ENVIRONMENT` - Environment variable override

Example `/etc/rmrf.env`:
```json
{"env": "prod", "signature": "sha256:..."}
```

The environment determines which protection level is applied. You can override detection with:

```bash
rmrf shell --environment-override staging
```

## Directory Structure

rmrf uses the following directory structure:

```
/var/lib/rmrf/
├── plans/          # Stored deletion plans
├── backups/        # Versioned file backups
│   ├── dev/       # Development backups
│   ├── staging/   # Staging backups
│   └── prod/      # Production backups
└── audit/          # Audit trail logs
```

Initialize these directories with:

```bash
rmrf init
```

Or specify a custom root directory:

```bash
rmrf init --root-dir /custom/path
```

## Custom Protection Levels

You can define custom protection levels in `/etc/rmrf/protection_levels.d/*.yaml`:

```yaml
name: audit-strict
description: "High audit retention mode"
max_files: 1000
max_bytes: 1073741824  # 1 GB
require_backup: true
require_audit: true
require_confirmation: false
retention_days: 30
```

See [Protection Levels](protection-levels.md) for more details on creating custom protection levels.
