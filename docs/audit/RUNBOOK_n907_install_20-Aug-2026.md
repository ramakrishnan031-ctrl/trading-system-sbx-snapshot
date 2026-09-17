# RUNBOOK — INSTALL `n907` ONLY, EVENING 20-Aug-2026

**Ruled by Rama 20-Aug:** *"n907 GO tonight, tiers HOLD pending a clean measurement."*
🔴 **ONE UNIT TONIGHT. ⛔ `tiers` DOES NOT GO.** ⛔ Nothing pushes without Rama's **quoted go**
at the gate — this runbook is preparation, ⛔ not authorisation.

**THE UNIT:** `d8969687306ad9fe37a7e99b606e9a3902d88c72`
· branch `fix/n907-extract-18aug` · parent `08b462ba175d904e8723ed34a13c956f0dd33679`
· **2 files, +154 / −2**: `scripts/forward_shadow_record.py`, `tests/unit/test_n907_forward_shadow_encoding.py`
· prediction `docs/audit/PREDICTION_n907_19-Aug-2026.md`, frozen md5 **`679a4f460d2fa86cea69a1e2df5b50cd`** (selector `sed -n '1,168p'`)

---

## ⏰ TIMING — TWO HARD CONSTRAINTS

- 🔴 **A1 (`forward_shadow_record`) runs at 18:15.** ⛔ **NEVER run it by hand** — its output cannot
  be regenerated and a manufactured day is a CORRUPTION, not a repair.
- ⚠️ **`cron_officer_eod` runs 18:50.** ⛔ **Do NOT squeeze the push into the 18:45-18:50 gap.**
- ⚠️ **18:15 is the push FLOOR, ⛔ not a clear window.** Clear slot ≈ **after 19:00** — ⛔ but the
  clock is NOT the test; the gates are.

---

## GATE A1 — 🔴 THE **ROW COUNT**, ⛔ NOT `status=SUCCESS`

```
ssh trading-vm 'sqlite3 -header "file:/home/ubuntu/systems/trading-system/data_store/trading_system.db?mode=ro" \
 "SELECT executed_at, status, message FROM cron_heartbeat WHERE job_name=\"forward_shadow_record\" ORDER BY id DESC LIMIT 3;"'
```

🔴 **PASS ⇔ the newest row is dated `2026-08-20` AND its `message` carries `wrote=<N>` with N > 0.**
⛔ **`status = SUCCESS` IS NOT SUFFICIENT AND HAS ALREADY BEEN WRONG ONCE:**

> `2026-08-10T18:15:02 | SUCCESS | [func=EMPTY_NO_DATA] date=2026-08-10 nothing new (0 present)`

⛔ **0 rows ⇒ DEFER.** ⚠️ A `PARTIAL` may satisfy A2 — ⛔ **never relabel it SUCCESS.**

**THE UNCHANGED BASELINE (banked BEFORE the unit can ship — this is the pre-image):**
`19-Aug wrote=4265 sim=3744` · `18-Aug 5917/5546` · `17-Aug 5962/5679` · `14-Aug 5567/5294` ·
`13-Aug 5466/5122` · `12-Aug 5425/5180` · `11-Aug 6750/6329` · **`10-Aug EMPTY_NO_DATA 0`** ·
`07-Aug 6198/5875` · `06-Aug 7947/7898` · `05-Aug 8675/8596`.
⭐ **Tonight's 18:15 run is the LAST UNPATCHED reading.** The first POST-deploy run is
**21-Aug 18:15**, and it is a **before/after comparison**, ⛔ never a new baseline.

## GATE B — THE 17:35 SELF-EXIT, **PATH NAMED** (⛔ `inactive` alone is vacuous)

**The path:** `main._start_eod_self_exit_thread` → `main._eod_self_exit_due()`, reading
`trading_hours.service_window_end` (`core/config_loader.py:98`, default `16:00`, **configured
`17:35`**). ⭐ **Three artifacts must agree, ⛔ not one:**

1. `logs/system_2026-08-20.log` contains
   `"logger":"main","msg":"eod_self_exit: past 17:35 IST and flat (0 active positions) — clean shutdown for the day…"`
2. `journalctl -u trading-system.service` shows `Deactivated successfully.`
3. `systemctl show trading-system.service -p ActiveState -p SubState -p Result -p ExecMainStatus`
   ⇒ `inactive` / `dead` / `Result=success` / `ExecMainStatus=0`

⚠️ **If a DELIVERY POSITION CARRIES, the service will NOT self-exit** (`0 active positions` is the
condition). ⇒ **the manual stop IS owed and ⛔ RAMA TYPES IT.** ⛔ **Do not use `sudo`.**
⛔ **NEVER `restart`/`start` while a manual stop is standing** — read
`kill_switch_state.triggered_at` FIRST.

## GATE C — `origin/main`, **TWO INDEPENDENT WAYS**, AT THE GATE

```
git ls-remote origin refs/heads/main                                    # PC, wire protocol
ssh trading-vm 'cat /home/ubuntu/trading-system.git/refs/heads/main'    # VM, filesystem, no git binary
```
⛔ **The cached local `origin/main` ref is NOT a second measure.**
🔴 **EXPECTED `08b462ba175d904e8723ed34a13c956f0dd33679`. If it moved, STOP and re-plan** — a
different base invalidates the gate AND the prediction's base-staleness clause.

```
git push --dry-run origin d8969687306ad9fe37a7e99b606e9a3902d88c72:refs/heads/main
```
⇒ must read `08b462b..d896968` **fast-forward**, rc 0.
✅ Measured 08:5x today: **rc 0, `08b462b..d896968`.** ⛔ Re-measure anyway — a comparand written
hours earlier tells you NOTHING (12-Aug proved it).

## GATE D — THE PUSH

```
git push origin d8969687306ad9fe37a7e99b606e9a3902d88c72:refs/heads/main
```
⛔ **NEVER `git push origin main`.** ⛔ **NEVER `--force`.** ⛔ **DO NOT START THE SERVICE** —
`post-receive` does not start it, and that is correct.

**D6.1 — crontab md5 BEFORE the push.** Baseline **`b8276da7043975cda2d0ce6578960c6a`**,
**46 job lines** (re-measured today, unchanged). Post-push md5 must **equal** pre-push.

## GATE E — VERIFY AFTER

**E1 · md5 PC == VM, PC side FROM THE REF'S BLOBS** (⛔ not the working tree):
```
git show d896968:scripts/forward_shadow_record.py | md5sum
git show d896968:tests/unit/test_n907_forward_shadow_encoding.py | md5sum
ssh trading-vm 'cd /home/ubuntu/systems/trading-system && md5sum scripts/forward_shadow_record.py tests/unit/test_n907_forward_shadow_encoding.py'
```

**E2 · deployed-tree drift — 🔴 USE THE CORRECTED RECIPE:**
```
ssh trading-vm 'export GIT_INDEX_FILE=/tmp/idx_probe && rm -f /tmp/idx_probe
G="--git-dir=/home/ubuntu/trading-system.git --work-tree=/home/ubuntu/systems/trading-system"
git $G read-tree d8969687306ad9fe37a7e99b606e9a3902d88c72
git $G update-index --refresh -q            # <-- WITHOUT THIS IT REPORTS 1,309 PHANTOM FILES
git $G diff-files --name-status              # EMPTY == no tracked drift
rm -f /tmp/idx_probe'
```
⛔ **The uncorrected form reports 1,309 files modified on an IDENTICAL tree and `P3` would fire
falsely.** ⭐ Pair it with the `md5sum`-vs-blob control above — two methods that agree.

**E3 · `origin/main` two ways AGAIN** ⇒ both `d896968`. **E4 · crontab md5 == pre-push.**

## GATE F — RECORDS, SAME NIGHT

- 🏷️ **`DEPLOYED`, ⛔ NOT `VERIFIED LIVE`.** ⭐ Ceiling for this unit is **`DEPLOYED`** and
  `VERIFIED LIVE` is **UNREACHABLE** (no presence signature — see the prediction §B/§E).
- 📓 **`MASTER_REGISTER.md`** (`D:\Projects\trading-system-main\docs\`) — new rows, **committed
  ⛔ NOT pushed**. ⚠️ Next id is **`N20-01`**; ⛔ **no `N19-*` rows exist** — 19-Aug went
  unregistered and that gap should be noted, ⛔ not silently filled.
- 🧠 Four memory targets · `SYSTEM_MAP.md` · `PATHS.md` · `UNPUSHED_PENDING_DEPLOY_LEDGER`.
- 📌 Append **ADDENDUM 2** to the n907 prediction with the install result. ⛔ Below the boundary;
  re-verify **`679a4f460d2fa86cea69a1e2df5b50cd`** after.

## ⛔ PROHIBITIONS TONIGHT
⛔ tiers does **NOT** go — ⛔ do not push `b80354c`, `7297be7`, `7d1fd4e`, `3cf3729`, `65b7196`.
⛔ No F6 (`c39e799`), no controlplane (`5cdd7e9`), no GUI. ⛔ No combined unit.
⛔ Do not start the service. ⛔ No DB write, no migration, no `SYNC`, no ledger edit.
⛔ Do not run `forward_shadow_record.py` manually. ⛔ Do not commit/switch/clean the root worktree.
⛔ Do not delete or amend `b80354c` / `7297be7` / any tag. ⛔ No `rm -rf` under `D:\Projects\`.
⭐ **A clean deferral beats a false deployment.**

## 🧹 CLEANUP OWED (⛔ after the install, ⛔ not before)
Five throwaway gate worktrees registered under the session scratchpad —
`gate-base` · `gate-n907` · `gate-tiers` · `gate-tiersR` · `tiers-work` · `tiers-rebase` —
remove with **`git worktree remove`** only (⛔ no `--force`, ⛔ no `rm -rf`), then verify
**heads and tags UNCHANGED** and that `b80354c` / `7297be7` still resolve.
⚠️ Also standing: a stale `basegate` worktree at `6fa8a1c` from an EARLIER session's scratchpad.
