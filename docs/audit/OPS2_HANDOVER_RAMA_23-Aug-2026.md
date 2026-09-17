# OPS ② — HAND-OVER TO RAMA · option (ii), IN-PLACE · **⛔ NOT APPLIED**

**23-Aug-2026, IST.** Governed by `docs/PRE_BUILD_REVIEW_GATE.md` (`23ea03d`).

🏷️ **STATUS: `PREPARED · ⛔ NOT APPLIED · ⛔ NO VM WRITE · ⛔ NO sudo RUN`.**
⛔ I am denied `sudo`. Every VM fact below is carried forward from the **read-only**
measurement recorded in `docs/audit/OPS2_EXIT5_PREPARED_22-Aug-2026.md` (22-Aug evening:
`cat`, `ls`, `md5sum`, `systemctl show`, `systemctl cat`, `journalctl`, `sed -n`, `grep`).
⛔ **Nothing was re-measured on the VM today** — ⚠️ so §0's pre-check below is not a
formality: it re-establishes the anchor before anything is written.

**Supersedes the recommendation in `OPS2_EXIT5_PREPARED`** (which recommended the
drop-in). ⭐ Rama has ruled **(ii)**.

---

## THE RULING AND ITS REASON — recorded

**Option (ii): edit the installed unit file in place. ⛔ Not the drop-in.**

> The CRITICAL integrity alert is **CONFIRMATION** that the change landed and that the
> watch works. The drop-in lands in
> `/etc/systemd/system/trading-system.service.d/`, a directory the integrity monitor
> does **not** cover (**NI-15**) — so it would yield ENFORCEMENT with **no DETECTION**.

Measured support: `scripts/security_monitor.py:219` watches
`/etc/systemd/system/trading-system.service` by **exact path**, severity **CRITICAL**,
label `unit_trading`. The `.service.d/` directory appears nowhere in
`_default_watched_files()` (`:215-226`) — ⭐ that absence is the whole of NI-15.

---

## THE CHANGE — one token

```
RestartPreventExitStatus=3 4      →      RestartPreventExitStatus=3 4 5
```

⛔ Nothing else. `Restart=on-failure`, `RestartSec=10`, `StartLimit*`, `KillSignal`,
`TimeoutStopSec` untouched. Exits **0, 1, 2** keep today's behaviour exactly.

**Why:** exit 5 = config REJECTED at load (`main.py:1862` @ `4568385`). Without `5` in
that list systemd restarts every 10 s **forever**, the unit never reaches `failed`, and
`token_watcher.sh:139-141` reads `ActiveState=activating` as *"running — nothing to do"*
⇒ **no alert ever reaches the operator.** The rate limiter cannot save this:
`RestartSec=10` ≥ `StartLimitIntervalSec=10s` makes the burst threshold structurally
unreachable — proven live on this box by `security-watcher` at **71,433** restarts,
never once limited.

---

## ⏰ TIMING — BEFORE THE CODE SHIPS

⭐ Run this **before** either push in §4. F1 + NI-4 make **seven** delivery keys able to
route a missing-or-null value into `main.py:1862`. The protection must exist *when those
keys first become reachable*, not after.

⚠️ ⛔ Exit 5 is **not created by F1** — it has been reachable from any malformed YAML for
as long as `:1862` has existed, and has **never fired in ~73 days of journal**. F1 widens
the **aperture**, it does not create the exposure. `LATENT`, not `LIVE`.

---

## THE SEQUENCE — run in a shell **ON the VM**

⚠️ Run these directly in a VM shell, ⛔ **not** nested inside `ssh '...'` — nested SSH
quoting is how this campaign has mangled file content before.
⚠️ **Precondition: the service must be DOWN.** A bad edit then cannot break a live
session. As of 21-Aug 17:35 it was `inactive/dead`, last exit **0**, `NRestarts=0`.

### 0 · PRE-CHECK — establish the rollback anchor

```bash
systemctl show trading-system.service -p ActiveState -p SubState -p ExecMainStatus
systemctl show trading-system.service -p RestartPreventExitStatus
md5sum /etc/systemd/system/trading-system.service
```

Expected — ⛔ **if any of these three differs, STOP and re-measure; do not proceed:**

| | expected |
|---|---|
| state | `ActiveState=inactive`  `SubState=dead` |
| policy | `RestartPreventExitStatus=3 4`  ← the rollback anchor |
| md5 | `136a4e88774fb5d2f392688a2ce40d3e` (1411 B, 18-Jun 16:35) |

### 1 · BACKUP

```bash
sudo cp -p /etc/systemd/system/trading-system.service \
           /etc/systemd/system/trading-system.service.bak-23aug2026
md5sum /etc/systemd/system/trading-system.service.bak-23aug2026   # must equal 136a4e88…
```

### 2 · ANCHORED EDIT

```bash
sudo sed -i 's/^RestartPreventExitStatus=3 4$/RestartPreventExitStatus=3 4 5/' \
           /etc/systemd/system/trading-system.service
grep -n '^RestartPreventExitStatus=' /etc/systemd/system/trading-system.service
#   must now read exactly:  RestartPreventExitStatus=3 4 5
```

⭐ The pattern is anchored at both ends (`^…$`) against the line **as measured**, so it
matches once or not at all. If `grep` still shows `3 4`, the anchor missed — ⛔ do not
loosen the pattern; STOP and report the actual line.

### 3 · DAEMON-RELOAD

```bash
sudo systemctl daemon-reload
```

⭐ `daemon-reload` does **not** start or restart anything. The unit is inactive; the new
policy applies at the next exit. ⛔ No restart is needed and none should be done.

### 4 · VERIFY ENFORCEMENT — 🔴 this is the acceptance test

```bash
systemctl show trading-system.service -p RestartPreventExitStatus
#   MUST print exactly:  RestartPreventExitStatus=3 4 5
```

⛔ Reading the FILE is **not** enough. A syntax error or a missed `daemon-reload` leaves
the file right and the policy wrong. **Only `systemctl show` answers "did it load".**

### 5 · CONFIRM SERVICE STATE — unchanged

```bash
systemctl show trading-system.service -p ActiveState -p SubState -p NRestarts
#   expect still:  inactive / dead / NRestarts=0   (the edit must not have started it)
```

### 6 · CONFIRM THE INTEGRITY WATCHER FIRED — DETECTION

Wait **~60 s** (the watcher's `RestartSec=60` heartbeat cadence), then:

```bash
journalctl -u security-watcher --since '-5 min' | tail -40
```

Expect **one CRITICAL**, of the form
`Sensitive file changed: unit_trading` — `/etc/systemd/system/trading-system.service`
`content changed (sha256 <old12>→<new12>)`
(`scripts/security_monitor.py:730-740`), and the matching Telegram.

⛔ **If no CRITICAL arrives, do NOT proceed to §7 and do NOT assume success** — it means
the integrity watch is not working, which is itself a finding worth more than this fix.

### 7 · THE BASELINE — 🔴 READ THIS BEFORE RUNNING ANYTHING

🔴 **CORRECTION TO THE INSTRUCTED SEQUENCE. There is no re-bless step to run, and
running one would be actively harmful.**

**Measured at `scripts/security_monitor.py:721-742`:** `check_watched_files` writes
`hashes[path] = cur` **before** it compares, and persists `state["file_hashes"]` at the
end of **every** `--watch` pass. ⇒ the very pass that fires the CRITICAL has **already**
stored the new hash. The next pass is silent on its own.

⇒ **The re-bless is automatic and unavoidable. `--baseline` is NOT required here.**
⭐ Corollary worth keeping: the operator gets **exactly one** CRITICAL, not a repeating
one. **If it repeats, something else is wrong** — investigate, do not silence it.

⛔ **DO NOT run `security_monitor.py --baseline` to "tidy up".** It seeds **every**
watched item as known-good in one shot — `sshd_config`, `/etc/sudoers`,
`authorized_keys`, `.env`, and new-login-IP state (`:778` *"baseline / first run — seed
silently"*). Anything else that changed since the last baseline would be **silently
granted amnesty**. That is a blind pardon across the whole security surface to solve a
problem that solves itself.

✅ **If you want positive confirmation instead**, this is read-only and safe:

```bash
cd /home/ubuntu/systems/trading-system
/home/ubuntu/systems/venv/bin/python scripts/security_monitor.py --report
#   --report is explicitly "human-readable status; no alerts/state" (:1313)
```

### 8 · RECONCILE THE REPO COPY — its own commit, ⛔ not mixed with anything

`deploy/systemd/trading-system.service:35` still reads `RestartPreventExitStatus=3 4`.
Bring it to `3 4 5` in a **standalone commit** whose message records that **installing a
unit file is a manual VM act that deploy does not perform**.

🔴 **AND STATE THE RESIDUAL DRIFT, or the next reader will misdiagnose it.** After both
the VM edit and this commit, the two files are **still not identical**:

| | md5 |
|---|---|
| installed (before this change) | `136a4e88774fb5d2f392688a2ce40d3e` |
| repo copy @ `4568385` | `e24b88493bc5cdd7ff7753479a73a8dc` |

They differ by **two comment lines** about exit 4 that were expanded in git and never
re-installed — ⭐ every *directive* is already identical. Reconciling the one token does
**not** make the md5s match, and ⛔ nobody should later "fix" that by copying the repo
file over the installed one without re-reading this note.

### ROLLBACK — one command

```bash
sudo cp -p /etc/systemd/system/trading-system.service.bak-23aug2026 \
           /etc/systemd/system/trading-system.service
sudo systemctl daemon-reload
systemctl show trading-system.service -p RestartPreventExitStatus
#   MUST print:  RestartPreventExitStatus=3 4
```

⚠️ Rollback also changes the file ⇒ it fires a **second** integrity CRITICAL. That is
correct behaviour, not a fault.

---

## 🔴 THREE EVIDENCES — ⛔ NEVER COLLAPSED

| evidence | what it proves | ⛔ what it does NOT prove | step |
|---|---|---|---|
| **DETECTION** — the integrity CRITICAL fires | the watch **saw the file change** | ⛔ **nothing** about whether the policy loaded | §6 |
| **ENFORCEMENT** — `systemctl show -p RestartPreventExitStatus` prints `3 4 5` | systemd is **using** the new policy | ⛔ nothing about whether anyone would be told | §4 |
| **GOVERNANCE** — repo copy reconciled in its own commit, residual drift stated | the change is **recorded where the next reader looks** | ⛔ nothing about the running system | §8 |

⭐ **"The alert fired" proves DETECTION and nothing else.** ENFORCEMENT is the only one
that answers *"did the fix work"*. All three must be collected.

---

## ⛔ WHAT THIS DOES **NOT** FIX — restated, before and after

1. **The alert still does not name the key.** After this change exit 5 reaches `failed`
   and `token_watcher.sh` falls to its `1|2|*)` default:
   *"trading-system crashing (exit 5); restart backoff limit reached. Manual check
   needed."* ⛔ **It does not say which config key was rejected.** The key name exists
   only in the CRITICAL written to `logs/system_<date>.log`. Wiring it into the alert is
   the boot-path alert work — ⭐ still queued, ⛔ not done.

2. 🔴 **Exits 1 and 2 remain in the alert-guard trap — before this change and after.**
   `clear_alert_flags()` fires on `active` **or** `activating` and deletes the
   once-per-day flags. systemd still auto-restarts exits 1 and 2, which still report
   `ActiveState=activating`, so they still hit `clear_alert_flags` on every 30 s poll.
   ⭐ **The defect was never exit-5-specific.** This change only makes it unreachable
   *via exit 5*. `LATENT`, ⛔ not fixed, ⛔ not in scope.

3. **It is not a clean stop — it is up to 3 futile boots per hour.** Exit 3 has a
   dedicated *"failed today ⇒ NOT restarting"* branch; exit 5 has none, so it takes the
   crash path and `start_service` runs up to `MAX_CRASH_PER_HOUR=3` before alerting.
   ⭐ Derived from the constants (⛔ not measured — exit 5 has never occurred): roughly
   **2 minutes** from an 08:15 failure to the first Telegram — against **no alert at
   all** today. Giving exit 5 exit-3's branch is the natural follow-up; ⛔ not done.

4. **OPS ① (`OnFailure=`) is still the only catch-all** for a failure mode nobody has
   enumerated. This fixes **one** exit code. ⭐ Still queued, ⛔ not done.

---

## ⛔ NOT DONE HERE

⛔ Not applied · ⛔ no `sudo` · ⛔ no VM write · ⛔ no service state change · ⛔ repo copy
**not** committed (§8 is Rama's to run or to authorise) · ⛔ NI-15 not resolved ·
⛔ `token_watcher.sh` not touched.
