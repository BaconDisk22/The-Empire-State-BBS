# TCP health and recovery

The reported Intel Mac test used `10.0.0.76:4403`: after the radio became
unreachable, the app continued to show Running/Ready. The old server had no
post-startup health check and its supervisor latched readiness from a log line.
This change is tested with simulated failures, not radio hardware. No hardware
verification or RF delivery verification is claimed.

The server owns one Meshtastic TCP session. After initialization it requests
read-only device metadata from the **local node number** over that session.
A matching metadata response establishes local protocol responsiveness, not RF
coverage, remote delivery, or the health of other nodes. Socket acceptance,
successful writes, routing ACKs, and silence on mesh channels do not establish
protocol health. No extra TCP probe socket is opened while the BBS runs.

Health states shown by the desktop:

- CONNECTING / CHECKING: startup or first protocol check pending.
- RESPONSIVE: a recent local metadata response; RF delivery remains unverified.
- UNRESPONSIVE: metadata deadline missed or request failed. This can mean a
  stalled session, network failure, firmware incompatibility, or congestion;
  it is **not** a claim that TCP is unreachable.
- DISCONNECTED: the owned transport failed or the library lost its connection.
- FAILED: startup or another server operation failed; see the error log.

Checks run immediately after initialization, then 30 seconds after completion.
The response deadline is 15 seconds. The first missed response displays a
warning; two consecutive misses stop the session with a nonzero exit status.
A valid reply on the next check clears the miss count. Late replies to expired
checks do not restore health. Detection after a previously successful check is
normally within about 45 seconds for the first warning and 90 seconds for exit,
plus scheduling and bounded send time. This is not a hard real-time guarantee.
Unsupported metadata replies also fail this check; inspect logs and firmware
compatibility before enabling automatic recovery.

The Meshtastic client is pinned to 2.7.11 because the TCP adapter overrides its
internal reconnect, queue, and stream hooks. Re-test those hooks before upgrading.
Optional blocking JS8Call I/O runs in a daemon worker with its SQLite connection
created there, so it cannot stall the health loop or hold the process open.
TCP connect/read/write operations have a five-second timeout; idle reads are
normal. Queue-space waits are bounded to ten seconds. Library reconnect attempts
are disabled so reader/writer threads cannot race desktop retries. Interface
cleanup runs on normal exit and errors; a new process starts only after the old
process has exited. Stop terminates and waits for the process (and kills it if
needed), releasing its sockets before another Start.

**Auto recovery (crash / radio loss)** is off by default. If selected, the desktop
restarts an exited server after 2, 4, 8, 16, 32, then at most 60 seconds per attempt.
The delay does not reset merely because startup succeeds, avoiding rapid flapping.
Stop clears pending recovery and the counter. Turning recovery off or enabling
demo cancels a pending retry. Command-line server runs exit on failure and do not
reconnect themselves. Existing external service managers may apply their own
restart policies; configure those separately.

## Pending Intel Mac acceptance checks

1. Start with recovery off. Confirm CHECKING then RESPONSIVE with the local
   radio; no second device is required for this local protocol check.
2. Disconnect radio power or network. Record timestamps for warning and process
   exit; confirm the dashboard no longer reports responsiveness.
3. Restore the radio. With recovery off, confirm a manual Start is required.
4. Repeat with recovery enabled. Confirm increasing retry delays, a single active
   server/session, and a fresh metadata response before RESPONSIVE appears.
5. During retry, use Stop or turn recovery off; confirm no later connection.
6. While running, click preflight; it must refuse to open another connection.
7. Test network blackholing separately from clean socket closure, and keep an
   otherwise idle but connected radio running to check for false warnings.
8. RF delivery remains a separate test requiring another node.

Automated tests cover protocol replies, timeouts, stale/invalid responses, socket
EOF/errors, suppression of library reconnect, queue deadlines, lifecycle cleanup,
supervisor readiness, backoff, opt-out, Stop, and preflight exclusion. Both CI
unit-test jobs now discover the full test suite, including radio tests previously
omitted by their filename filter.
