# Code Review: Phase 6 - Server Deployment & Access

## Gate: PASS

**Summary:** Implementation delivers on all acceptance criteria. Systemd service, deployment script, Raycast scripts, and documentation are all present and functional. Two major issues identified (missing ReadWritePaths for KB directory, no network access control) are acceptable given the personal/Tailscale context but documented for awareness. All 52 tests pass.

---

## Git Reality Check

**Commits:**
```
e08763d docs(tasks): update T015 main.md with Phase 6 execution log
66cdff8 Phase 6: Server deployment and access
```

**Files Changed (HEAD~2):**
```
CLAUDE.md
deploy/deploy-kb-serve.sh
deploy/kb-serve.service
scripts/raycast/open-kb-browse.sh
scripts/raycast/open-kb-dashboard.sh
tasks/global-task-manager.md
tasks/planning/T015-kb-serve-dashboard/main.md
```

**Matches Execution Report:** Yes - all claimed files are present in commits.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| Systemd service file created and documented | Yes | Yes | `deploy/kb-serve.service` with security hardening directives |
| Deployment script works | Yes | Yes | `deploy/deploy-kb-serve.sh` handles install/status/logs/restart/stop/uninstall |
| Documentation explains local and server setup | Yes | Yes | CLAUDE.md updated with KB Server Deployment section |
| Raycast scripts for quick access | Yes | Yes | Two scripts in `scripts/raycast/` with proper Raycast metadata |

---

## Issues Found

### Major

1. **Missing ReadWritePaths for KB directory**
   - File: `deploy/kb-serve.service:31`
   - Problem: Service has `ReadWritePaths=/home/blake/.kb` but the KB_ROOT is `~/Obsidian/zen-ai/knowledge-base/transcripts`. On the server (zen), this maps to `/home/blake/lem/mac-sync/Obsidian/zen-ai/knowledge-base/transcripts`. The service will fail to scan or write to the actual KB directory due to `ProtectHome=read-only`.
   - Fix: Either add the KB path to ReadWritePaths or document that config file must override `kb_output` to a location under `~/.kb/`.
   - Impact: Service will run but fail to read transcripts without config override.

2. **No network access control on 0.0.0.0 binding**
   - File: `deploy/kb-serve.service:16`
   - Problem: Binding to `0.0.0.0:8765` exposes the dashboard to all network interfaces without authentication. While Tailscale provides some protection, the dashboard itself has no auth.
   - Fix: Document the security model explicitly (relies on Tailscale ACLs) or consider binding to Tailscale interface only.
   - Impact: Low for personal use case with Tailscale. Anyone on the Tailscale network can access.

### Minor

1. **Missing newline at end of CLAUDE.md**
   - File: `CLAUDE.md`
   - Problem: File ends without trailing newline (git diff shows `\ No newline at end of file`).
   - Impact: Style only, but violates POSIX file convention.

2. **Raycast scripts use hardcoded `zen` hostname**
   - File: `scripts/raycast/open-kb-dashboard.sh:18`, `scripts/raycast/open-kb-browse.sh:18`
   - Problem: Hostname `zen` is hardcoded. Won't work if Tailscale hostname changes or user has different setup.
   - Impact: Documentation issue. User would need to edit scripts.

3. **Deployment script assumes `blake` user**
   - File: `deploy/kb-serve.service:10-11`
   - Problem: User/Group hardcoded to `blake`. Not portable to other users.
   - Impact: Expected for personal project, but could document.

4. **No validation in deployment script for service file syntax**
   - File: `deploy/deploy-kb-serve.sh`
   - Problem: Script copies service file without validating systemd unit syntax first.
   - Fix: Add `systemd-analyze verify $SERVICE_FILE` before copy.
   - Impact: Minor - bad syntax would show on systemctl start anyway.

---

## What's Good

- Deployment script is well-structured with clear commands (install/status/logs/restart/stop/uninstall)
- Security hardening in systemd service (ProtectSystem, ProtectHome, NoNewPrivileges, PrivateTmp)
- Raycast scripts have proper metadata for Raycast integration
- Documentation in CLAUDE.md is clear and provides both local and server usage
- File permissions correctly set (scripts executable)
- Start rate limiting configured to prevent rapid restart loops
- All 52 tests pass

---

## Required Actions (for REVISE)

Not required - PASS gate.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Systemd ReadWritePaths must cover all write locations | Future deployment configs | Audit all paths the service needs to access |
| Binding to 0.0.0.0 assumes trusted network | Network services | Document security model or implement auth |
| Server vs Mac path differences | Cross-platform deployment | Consider environment-specific configs |

---

## Security Notes (For User Awareness)

The 0.0.0.0 binding security model:
- **Tailscale network:** All Tailscale devices in your network can access http://zen:8765
- **No application-level auth:** Anyone on Tailscale can view/modify action queue
- **Acceptable because:** This is a personal tool on a personal Tailscale network

The ReadWritePaths issue:
- Service will fail to read KB transcripts without config
- User should create `~/.config/kb/config.yaml` with:
  ```yaml
  paths:
    kb_output: /home/blake/.kb/transcripts
  ```
  Or symlink `~/Obsidian` to the actual location.
