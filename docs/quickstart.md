# rmrf Quickstart Guide

Get up and running with **rmrf** - the safety-critical deletion utility - in 5 minutes.

## What is rmrf?

rmrf is a production-safe alternative to `rm -rf` that provides:
- **Policy enforcement** - Validate deletions against organizational rules
- **Reversible operations** - Automatic backups with rollback capability
- **Complete audit trails** - Every deletion is tracked and auditable

## Interactive Shell Mode (Recommended)

For a more streamlined workflow, use the interactive shell:

```bash
# Start interactive shell
rmrf shell

# Commands auto-track your active plan
rmrf:dev[safe-local]
plan: (none)
> plan /tmp/old-logs --scenario "cleanup"
→ Tracking plan: plan-tmp-old-logs-20251108-abc123 [planned]

rmrf:dev[safe-local]
plan: plan-tmp-old-logs-20251108-abc123 | stage: planned
> validate plan-tmp-old-logs-20251108-abc123
→ Tracking plan: plan-tmp-old-logs-20251108-abc123 [validated]

# Use tab completion for commands and plan IDs
> stage <TAB>
> apply <TAB>
```

**Shell features:**
- Automatic plan tracking through workflow stages
- Tab completion for commands and plan IDs
- Command history with readline
- Persistent environment display
- Session state tracking

## Installation

### Option 1: Download Binary (Recommended for modern systems)

**Requirements:** GLIBC 2.35+ (Ubuntu 22.04+, Debian 12+, RHEL 9+, Fedora 35+)

Check your GLIBC version:
```bash
ldd --version | head -1
# Should show 2.35 or higher
```

The binary is built on Ubuntu 22.04 for compatibility with modern Linux distributions.

Download the latest pre-built binary:

```bash
# Download binary and checksum
wget https://github.com/ccollicutt/rmrf/releases/latest/download/rmrf
wget https://github.com/ccollicutt/rmrf/releases/latest/download/SHA256SUMS

# Verify checksum
sha256sum -c SHA256SUMS

# Install
chmod +x rmrf
sudo mv rmrf /usr/local/bin/

# Verify installation
rmrf --version
```

If you get a GLIBC error, your system is older than Ubuntu 22.04 - use Option 2 (Install from Source) instead.

### Option 2: Install from Source

Prerequisites:
- **Python 3.10+** (check with `python3 --version`)
- **uv** package manager ([install here](https://docs.astral.sh/uv/))

```bash
# Clone the repository
git clone https://github.com/ccollicutt/rmrf
cd rmrf

# Create virtual environment and install
uv venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .

# Verify installation
rmrf --version
```

## Initial Configuration

### 1. Initialize Directory Structure

Use `rmrf init` to create required directories:

```bash
# Create system-wide directories (requires sudo/permissions)
sudo rmrf init

# Or create user-level directories
rmrf init --root-dir ~/.rmrf
```

This creates:
- `plans/` - Deletion plan storage
- `backups/` - Backup files with SHA-256 verification
- `audit/` - Complete audit trail logs

### 2. Set Up Environment Detection

Create `/etc/rmrf.env` to define your environment:

```bash
sudo tee /etc/rmrf.env > /dev/null <<EOF
{
  "env": "dev",
  "signature": "sha256:dev-$(hostname)"
}
EOF
```

**Environment types:**
- `dev` - Development (least restrictive)
- `staging` - Staging environment
- `prod` - Production (most restrictive)

Alternatively, use an environment variable (useful for testing):

```bash
export RM_ENVIRONMENT='{"env":"dev","signature":"sha256:test"}'
```

### 3. Verify Setup

```bash
# Run preflight check to verify configuration
rmrf preflight

# Should show all checks passing
```

The preflight check validates:
- Environment detection working
- Protection levels loaded
- Plan store accessible
- Backup directory writable
- Audit directory writable

## Basic Usage - The Golden Path

rmrf uses a multi-step workflow for safe deletion:

### Step 1: Plan

Create a deletion plan by scanning target files:

```bash
# Plan a deletion
rmrf plan /tmp/old-logs --scenario "cleanup old logs"

# Output shows plan ID and next steps
# Plan ID: plan-20250107-120000-abc123de
```

**Options:**
- `--scenario` - Describe why you're deleting (for audit trail)
- `--output plan.json` - Save plan to file
- `--environment prod` - Override environment detection
- `--dry-run` - Create plan without actual deletion capability

### Step 2: Validate

Validate the plan against safety policies:

```bash
# Validate with built-in safety rules (production-ready)
rmrf validate plan-20250107-120000-abc123de
```

**Built-in validation checks:**
- Plan expiration
- File count and size limits (from protection levels)
- Environment-specific restrictions
- Risk-based approval requirements
- Production safety gates

### Step 3: Stage (Create Backup)

Create backup before deletion (required for most protection levels):

```bash
# Stage the plan - creates backup with SHA-256 verification
rmrf stage plan-20250107-120000-abc123de

# Output shows backup location and manifest ID
# Backup Location: /var/lib/rmrf/backups/20250107-120000-abc123de
```

**Staging features:**
- SHA-256 checksums for integrity
- Automatic retention management
- Rollback capability

### Step 4: Apply

Execute the deletion:

```bash
# Execute deletion (with confirmation prompt)
rmrf apply plan-20250107-120000-abc123de

# OR skip confirmation (use with caution)
rmrf apply plan-20250107-120000-abc123de --skip-confirmation

# OR dry-run to simulate
rmrf apply plan-20250107-120000-abc123de --dry-run
```

### Step 5: Verify

Verify the deletion was successful:

```bash
# Verify all target files were deleted
rmrf verify plan-20250107-120000-abc123de

# Output confirms deletion or shows files that still exist
```

**Verification checks:**
- All planned targets have been deleted
- Updates plan with verification status
- Can be run multiple times

### Step 6: Closeout

After confirming the deletion was successful, close out the plan:

```bash
# Mark plan as complete (keeps backup by default)
rmrf closeout plan-20250107-120000-abc123de

# OR remove backup to reclaim disk space
rmrf closeout plan-20250107-120000-abc123de --remove-backup
```

**Closeout options:**
- Default behavior keeps backup files for safety
- `--remove-backup` removes backup to reclaim disk space
- `--force` allows closeout even if plan wasn't applied (for cleanup)

**When to closeout:**
- After verifying the deletion was successful
- When you're confident you won't need to rollback
- To reclaim disk space from backups

## Complete Example - Golden Path

```bash
# 0. Initialize (first time)
rmrf init
export RM_ENVIRONMENT='{"env":"dev","signature":"test"}'
rmrf preflight

# 1. Create plan
rmrf plan /tmp/test-data --scenario "cleanup test data"
# Output: Plan ID: plan-20250107-120000-abc123de

# 2. Review plan
rmrf show plan-20250107-120000-abc123de

# 3. Validate (uses built-in validation)
rmrf validate plan-20250107-120000-abc123de

# 4. Stage (create backup)
rmrf stage plan-20250107-120000-abc123de
# Output: Manifest ID and backup location

# 5. Execute deletion
rmrf apply plan-20250107-120000-abc123de

# 6. Verify deletion
rmrf verify plan-20250107-120000-abc123de

# 7. Check status
rmrf status plan-20250107-120000-abc123de

# 8. Close out (keeps backup by default for safety)
rmrf closeout plan-20250107-120000-abc123de
```

## Rollback - Undo a Deletion

If you need to reverse a deletion:

```bash
# 1. Verify backup integrity
rmrf rollback manifest.json --verify-only

# 2. Restore files
rmrf rollback manifest.json

# All files restored to original locations with checksum verification
```

## Approval Workflow

For high-risk deletions, rmrf supports multi-user approval where a different user must approve the plan before execution.

### When Approval is Required

Plans automatically require approval when:
- Protection level has `require_approval: true`
- Validation returns `require_approval` verdict
- High-risk operations in production environments

### Approval Commands

```bash
# List plans waiting for approval
rmrf list-pending-approvals
rmrf list-pending-approvals --environment prod

# Approve a plan (must be different user than creator)
rmrf approve plan-20250107-120000-abc123de
rmrf approve plan-20250107-120000-abc123de --comment "Reviewed and approved"

# After approval, continue with normal workflow
rmrf validate plan-20250107-120000-abc123de --approval-id appr-abc123
rmrf stage plan-20250107-120000-abc123de
rmrf apply plan-20250107-120000-abc123de
```

### Locking

Plans automatically acquire locks on target directories to prevent concurrent operations:

```bash
# Release locks for a plan (cleanup/recovery)
rmrf unlock plan-20250107-120000-abc123de
```

Locks are automatically released when:
- Plan is applied successfully
- Plan is closed out
- Plan expires
