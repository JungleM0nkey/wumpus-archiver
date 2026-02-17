# Design: Matrix E2EE Encryption Enforcement

**Date:** 2026-02-16
**Status:** APPROVED
**Goal:** Prevent accidental unencrypted room creation on matrix.apehost.net

## Context

- Homeserver: `matrix.apehost.net` (Synapse, Docker, Cloudflare Tunnel)
- User base: Small trusted group (friends/family), all on Element clients
- Federation: Active (joins rooms on other servers)
- Current state: Zero encryption config — E2EE available but not enforced
- VoIP: Cloudflare TURN (Phase 1) + LiveKit Cloud (Phase 2) already deployed

## Approach: Client + Server + Well-Known (Three-Layer Enforcement)

Three independent enforcement points ensure encryption defaults are applied regardless of which client or method is used to create rooms.

### Layer 1: Synapse Server-Side Enforcement

**File:** `/opt/stacks/matrix-synapse/data/homeserver.yaml`

```yaml
encryption_enabled_by_default_for_room_type: "all"
```

- Synapse injects the encryption state event into every new room created on this server
- Applies to all clients (Element, FluffyChat, nheko, API calls)
- Value must be quoted (`"all"`) to avoid PyYAML interpretation issues
- Valid values: `"all"`, `"invite"` (private rooms only), `"off"`
- Only affects rooms created after this is set, not existing rooms

### Layer 2: Element Web Client Default

**File:** `/opt/stacks/matrix-synapse/element-config.json`

Add `io.element.e2ee` inside `default_server_config`:

```json
{
  "default_server_config": {
    ...existing keys...,
    "io.element.e2ee": {
      "default": true
    }
  }
}
```

- Encryption toggle defaults to ON in room creation dialog
- DMs always created encrypted
- Only affects users on the hosted Element Web instance

### Layer 3: Well-Known E2EE Policy

**File:** `/opt/stacks/matrix-synapse/well-known-matrix-client.json` (new)
**File:** `/opt/stacks/matrix-synapse/Caddyfile` (updated)

Serve a static `/.well-known/matrix/client` response via Caddy containing:

```json
{
  "m.homeserver": {
    "base_url": "https://matrix.apehost.net"
  },
  "m.identity_server": {
    "base_url": "https://vector.im"
  },
  "org.matrix.msc4143.rtc_foci": [
    {
      "type": "livekit",
      "livekit_service_url": "https://matrix.apehost.net"
    }
  ],
  "io.element.e2ee": {
    "default": true
  }
}
```

Caddyfile route (before the Synapse catch-all):

```caddyfile
@wellknown path /.well-known/matrix/client
handle @wellknown {
    header Content-Type "application/json"
    header Access-Control-Allow-Origin "*"
    respond `{contents of well-known-matrix-client.json}`
}
```

- CORS header required (browsers fetch well-known cross-origin)
- Consolidates `rtc_foci` (LiveKit) into well-known so Desktop/Mobile clients also discover group call support
- Any Element client (Desktop, iOS, Android) connecting to this server gets the E2EE default

## What This Guarantees

- Every new room created on matrix.apehost.net is encrypted (server enforcement)
- Every Element client defaults encryption ON in the UI (client + well-known)
- Element Call inherits room encryption (calls in encrypted rooms use E2EE via LiveKit's per-participant keys)
- Federated rooms unaffected (can still join unencrypted rooms on other servers)

## What This Does NOT Do (By Design)

- Does not retroactively encrypt existing unencrypted rooms (Matrix protocol: encryption is irreversible but not retroactive)
- Does not prevent joining unencrypted federated rooms
- Does not block unencrypted room creation if a client ignores both well-known and server policy (only server enforcement layer handles forced override)

## Call Encryption Details

Element Call E2EE is automatic when the underlying Matrix room is encrypted:
1. Call signaling events are encrypted via the room's Megolm session
2. LiveKit media uses per-participant E2EE keys derived from the Matrix session
3. LiveKit Cloud servers cannot decrypt media content
4. No additional configuration needed beyond room-level encryption

## Files Changed

| File | Action |
|---|---|
| `/opt/stacks/matrix-synapse/data/homeserver.yaml` | Add `encryption_enabled_by_default_for_room_type: "all"` |
| `/opt/stacks/matrix-synapse/element-config.json` | Add `io.element.e2ee.default: true` |
| `/opt/stacks/matrix-synapse/well-known-matrix-client.json` | Create (new static file) |
| `/opt/stacks/matrix-synapse/Caddyfile` | Add `/.well-known/matrix/client` route |
| `/etc/komodo/stacks/matrix-synapse/compose.yaml` | Mount well-known JSON into Caddy |

## Sources

- [Element Web E2EE Docs](https://web-docs.element.dev/Element%20Web/e2ee.html)
- [Synapse encryption_enabled_by_default_for_room_type PR](https://github.com/matrix-org/synapse/pull/7639)
- [LiveKit E2EE Overview](https://docs.livekit.io/transport/encryption/)
- [Element Call E2EE Implementation](https://github.com/element-hq/element-call/issues/1278)
