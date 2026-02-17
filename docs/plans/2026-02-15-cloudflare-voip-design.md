# Design: Cloudflare VoIP Backend for Matrix Synapse

**Date:** 2026-02-15
**Status:** Approved

## Context

Existing Matrix Synapse homeserver running in Docker behind Cloudflare Tunnel. No TURN server configured (1:1 calls unreliable). No LiveKit/Element Call (no group calls). Goal: full voice, video, and screen sharing using Cloudflare infrastructure where possible.

## Approach

Incremental rollout in 3 phases. Cloudflare TURN first for immediate 1:1 calls, then LiveKit for group calls, with an optional future migration to Cloudflare SFU to eliminate LiveKit self-hosting.

## Phase 1: Cloudflare TURN (1:1 Calls)

**Components:**
- `matrix-turnify` — Python middleware container (port 4499)
- Cloudflare TURN App — API keys from Cloudflare Dashboard

**Architecture:**

```
Element Client
    |
    |  GET /_matrix/client/v3/voip/turnServer
    v
Cloudflare Tunnel (cloudflared)
    |
    |-- /voip/turnServer  --> matrix-turnify (:4499)
    |                            |
    |                            |-- auth check --> Synapse (:8008)
    |                            |-- credential gen --> Cloudflare TURN API
    |
    |-- everything else   --> Synapse (:8008)

During call:
    User A --WebRTC--> turn.cloudflare.com <--WebRTC-- User B
```

**How it works:**
1. Element client requests TURN credentials from Synapse endpoint
2. Cloudflare Tunnel routes the request to matrix-turnify (path-based ingress rule)
3. matrix-turnify forwards to Synapse for Matrix token validation
4. On success, calls `POST rtc.live.cloudflare.com/v1/turn/keys/{id}/credentials/generate-ice-servers`
5. Returns Cloudflare TURN credentials in Matrix-compatible format
6. Client uses `turn.cloudflare.com` for NAT traversal during call

**Configuration:**
- Docker Compose: add matrix-turnify service with `CF_TURN_TOKEN_ID`, `CF_TURN_API_TOKEN`, `SYNAPSE_BASE_URL`
- Cloudflare Tunnel: add ingress rule matching `^/.*/voip/turnServer$` before the Synapse catch-all
- Synapse: remove any existing `turn_uris` / `turn_shared_secret` config

**Why matrix-turnify is needed:** Synapse's native TURN config uses HMAC shared secret (draft-uberti-behave-turn-rest-00). Cloudflare uses its own REST API with Bearer token auth. The two are incompatible, so middleware translates between them.

**Effort:** Days
**Result:** 1:1 voice and video calls work in Element

## Phase 2: LiveKit + Element Call (Group Calls)

**Components:**
- LiveKit SFU — media server container
- lk-jwt-service — MatrixRTC authorization service container
- Synapse config update for MatrixRTC transport discovery

**Architecture:**

```
Element Client
    |
    |  1. MatrixRTC membership event (room state via Synapse)
    |  2. GET /_matrix/client/v1/rtc/transports --> discovers LiveKit
    |  3. Request JWT from lk-jwt-service
    |  4. Connect to LiveKit SFU via WebRTC
    v
Cloudflare Tunnel (TCP/HTTP only)
    |-- /_matrix/*          --> Synapse (:8008)
    |-- /voip/turnServer    --> matrix-turnify (:4499)
    |-- /lk-jwt/*           --> lk-jwt-service (:3000)

LiveKit SFU (direct, not tunneled)
    |-- TCP :7880 (WebSocket signaling)
    |-- UDP :50000-60000 (WebRTC media)
    |-- Uses Cloudflare TURN for client NAT traversal
```

**Networking constraint:** LiveKit SFU requires direct UDP connectivity for WebRTC media. Cloudflare Tunnel only carries TCP/HTTP. Therefore LiveKit needs:
- A host with a public IP (or port-forwarded)
- Ports open: 7880 TCP (signaling), 50000-60000 UDP (media)
- Own TLS termination or a subdomain (e.g., `lk.example.com`)

The lk-jwt-service (HTTP only) can go through the Cloudflare Tunnel.

**Configuration:**
- Docker Compose: add LiveKit SFU + lk-jwt-service containers
- LiveKit config: set TURN servers to Cloudflare TURN credentials
- Synapse: configure MatrixRTC to advertise LiveKit transport endpoint
- DNS: point `lk.example.com` directly to the LiveKit host (not proxied through Cloudflare)

**Effort:** 1-2 weeks
**Result:** Group voice/video calls and screen sharing work in Element via Element Call

## Phase 3: Cloudflare SFU Migration (Future, Optional)

**Goal:** Eliminate LiveKit self-hosting by replacing it with Cloudflare Realtime SFU.

**What it replaces:**
- LiveKit SFU container --> Cloudflare Realtime SFU (managed)
- lk-jwt-service --> Custom auth service on Cloudflare Workers + Durable Objects
- Open UDP ports --> Eliminated (all media through Cloudflare network)

**What it requires (if building yourself):**
- Custom MSC spec for `cloudflare_sfu` MatrixRTC transport (1-2 weeks)
- Auth/signaling service on Cloudflare Workers (4-6 weeks)
- Client transport plugin for Element Call (6-10 weeks)
- E2E encryption adaptation (4-6 weeks)
- Testing and stabilization (4-6 weeks)

**When to revisit:**
- Matrix community builds a Cloudflare SFU transport
- LiveKit maintenance becomes burdensome
- Need to eliminate public IP / open UDP port requirement

**Decision:** Park this. Phase 1 + 2 provide full functionality.

## Summary

| Phase | Delivers | Effort | New containers | Ports needed |
|---|---|---|---|---|
| 1 | 1:1 voice/video | Days | matrix-turnify | None (tunnel) |
| 2 | Group calls + screen share | 1-2 weeks | LiveKit SFU, lk-jwt-service | 7880 TCP, 50000-60000 UDP |
| 3 | Eliminate LiveKit (future) | Months | Workers (serverless) | None |

## Pricing

| Service | Free Tier | Paid |
|---|---|---|
| Cloudflare TURN | 1,000 GB/month | $0.05/GB |
| Cloudflare Tunnel | Free | Free |
| LiveKit SFU | Self-hosted | Infra cost only |

## References

See [docs/cloudflare-voip/](../cloudflare-voip/) for full research documentation and all sources.
