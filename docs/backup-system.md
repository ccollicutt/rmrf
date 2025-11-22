# Backup System

The backup system uses Python's standard library (shutil + hashlib) to create verified copies before deletion. This provides zero external dependencies while covering the most common use cases.

## What the Backup System Covers

- **Regular files** - Full copy with SHA-256 verification
- **Symlinks** - Preserved without following the link
- **Directory structure** - Preserved via relative paths
- **File metadata** - Permissions (mode), modification times (mtime), access times (atime)
- **Memory efficiency** - Checksums calculated in 8KB chunks
- **Error resilience** - Collects errors and continues backup
- **Versioned storage** - Organized by environment/date/plan_id

## Known Limitations

The backup system is designed for common deletion scenarios (cleanup of /tmp, /var/log, old builds, cache directories). It does not currently handle:

- **Empty directories** - Only files are backed up, empty directories are not preserved
- **Hard links** - Each hard link is copied as a separate file (not preserved as links)
- **File ownership** - User/group ownership (uid/gid) is not preserved
- **Extended attributes** - ACLs, SELinux contexts, and xattrs are not backed up
- **Special files** - FIFOs, device files, and Unix sockets are not supported
- **Sparse files** - Sparse files are expanded to full size during backup
- **Concurrent modification** - Files being written during backup may fail checksum verification

For typical cleanup tasks (removing temporary files, old logs, build artifacts), these limitations are acceptable. If you need to back up system configuration directories or files with special attributes, consider the limitations above.

## Backup Storage Structure

Backups are stored in `/var/lib/rmrf/backups/` organized by:

```
backups/
├── dev/
│   └── 2025-01-08/
│       └── plan-20250108-120000-abc123/
│           ├── manifest.json
│           └── files/
├── staging/
└── prod/
```

Each backup includes:
- **manifest.json** - Rollback manifest with checksums and metadata
- **files/** - Copied files preserving directory structure

## Rollback Process

To restore files from backup:

```bash
rmrf rollback plan-20250108-120000-abc123
```

The rollback process:
1. Reads the rollback manifest
2. Verifies backup integrity with SHA-256 checksums
3. Restores files to original locations
4. Preserves file permissions and timestamps
5. Verifies restoration success
