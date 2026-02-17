# Cloudflare VoIP for Matrix Synapse — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable full voice, video, and screen sharing for an existing Matrix Synapse homeserver using Cloudflare TURN (1:1 calls) and LiveKit (group calls).

**Architecture:** Incremental two-phase rollout. Phase 1 adds matrix-turnify as a sidecar container to provide Cloudflare TURN credentials for 1:1 calls. Phase 2 adds LiveKit SFU + lk-jwt-service for MatrixRTC group calls via Element Call. Both phases deploy as Docker containers alongside the existing Synapse.

**Tech Stack:** Docker Compose, cloudflared (Cloudflare Tunnel), matrix-turnify (Python), LiveKit SFU, lk-jwt-service, Synapse homeserver

---

## Phase 1: Cloudflare TURN (1:1 Calls)

### Task 1: Create Cloudflare TURN App

**Files:** None (Cloudflare Dashboard)

**Step 1: Create the TURN App in Cloudflare Dashboard**

1. Log into https://dash.cloudflare.com
2. Navigate to **Calls** in the left sidebar
3. Click **Create** > **TURN App**
4. Name it (e.g., `matrix-turn`)
5. Copy and securely save two values:
   - `TURN_KEY_ID` (the Token ID)
   - `TURN_KEY_API_TOKEN` (the API Token — shown once)

**Step 2: Verify the credentials work**

```bash
curl -X POST \
  "https://rtc.live.cloudflare.com/v1/turn/keys/$TURN_KEY_ID/credentials/generate-ice-servers" \
  -H "Authorization: Bearer $TURN_KEY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ttl": 86400}'
```

Expected: JSON response with `iceServers` array containing `stun.cloudflare.com` and `turn.cloudflare.com` entries with `username` and `credential` fields.

**Step 3: Store credentials securely**

Add to your Matrix server's `.env` file (or secrets manager):

```bash
CF_TURN_TOKEN_ID=<your-turn-key-id>
CF_TURN_API_TOKEN=<your-turn-api-token>
```

---

### Task 2: Deploy matrix-turnify Container

**Files:**
- Modify: Your Synapse `docker-compose.yml` (wherever your Matrix stack is defined)

**Step 1: Add matrix-turnify service to docker-compose.yml**

Add this service alongside your existing Synapse service:

```yaml
  matrix-turnify:
    image: ghcr.io/bpbradley/matrix-turnify:latest
    container_name: matrix-turnify
    environment:
      - SYNAPSE_BASE_URL=http://synapse:8008  # adjust container name/port to match your Synapse service
      - CF_TURN_TOKEN_ID=${CF_TURN_TOKEN_ID}
      - CF_TURN_API_TOKEN=${CF_TURN_API_TOKEN}
      - TURN_CREDENTIAL_TTL_SECONDS=86400
      - LOG_LEVEL=info
    user: "1000:1000"
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    restart: unless-stopped
    depends_on:
      - synapse  # adjust to match your Synapse service name
```

Notes:
- `SYNAPSE_BASE_URL` must resolve from within the Docker network to your Synapse container
- Do NOT expose port 4499 externally — only Cloudflare Tunnel will reach it
- Adjust `synapse:8008` to match your actual Synapse service name and port

**Step 2: Pull and start the container**

```bash
docker compose pull matrix-turnify
docker compose up -d matrix-turnify
```

**Step 3: Verify the container is running**

```bash
docker logs matrix-turnify
```

Expected: Startup log with no errors, listening on port 4499.

---

### Task 3: Configure Cloudflare Tunnel Ingress Rules

**Files:**
- Modify: Your `cloudflared` config file (typically `~/.cloudflared/config.yml` or `/etc/cloudflared/config.yml`)

**Step 1: Locate your current cloudflared config**

```bash
# Common locations:
# ~/.cloudflared/config.yml
# /etc/cloudflared/config.yml
# /opt/cloudflared/config.yml
# Or check: cloudflared tunnel list
```

Your current config likely looks something like:

```yaml
tunnel: <your-tunnel-id>
credentials-file: /path/to/credentials.json

ingress:
  - hostname: matrix.example.com
    service: http://synapse:8008
  - service: http_status:404
```

**Step 2: Add the matrix-turnify ingress rule BEFORE the Synapse catch-all**

```yaml
tunnel: <your-tunnel-id>
credentials-file: /path/to/credentials.json

ingress:
  # NEW: Route TURN credential requests to matrix-turnify
  - hostname: matrix.example.com
    path: ".*voip/turnServer$"
    service: http://matrix-turnify:4499

  # EXISTING: Everything else goes to Synapse
  - hostname: matrix.example.com
    service: http://synapse:8008

  # Required catch-all
  - service: http_status:404
```

Key points:
- The `path` field uses Go regex syntax
- The matrix-turnify rule MUST come before the Synapse rule (first match wins)
- `matrix-turnify:4499` must be reachable from the cloudflared container (same Docker network)

**Step 3: Validate the config**

```bash
cloudflared tunnel ingress validate
```

Expected: No errors.

**Step 4: Test rule matching**

```bash
cloudflared tunnel ingress rule https://matrix.example.com/_matrix/client/v3/voip/turnServer
```

Expected: Should match the matrix-turnify rule (rule index 0 or whichever is the turnify rule).

**Step 5: Restart cloudflared to apply**

```bash
# If running as a service:
sudo systemctl restart cloudflared

# If running in Docker:
docker compose restart cloudflared
```

---

### Task 4: Remove Native Synapse TURN Config (if any)

**Files:**
- Modify: Your Synapse `homeserver.yaml`

**Step 1: Check for existing TURN configuration**

Search your `homeserver.yaml` for any of these keys:

```yaml
turn_uris:
turn_shared_secret:
turn_user_lifetime:
turn_allow_guests:
```

**Step 2: Comment out or remove TURN settings**

If present, comment them out:

```yaml
# Removed — TURN credentials now provided by matrix-turnify + Cloudflare
# turn_uris: [...]
# turn_shared_secret: "..."
# turn_user_lifetime: ...
# turn_allow_guests: ...
```

**Step 3: Restart Synapse**

```bash
docker compose restart synapse
```

---

### Task 5: Test Phase 1 — 1:1 Calls

**Step 1: Test the TURN credential endpoint**

Get a Matrix access token (from Element's settings or via login API), then:

```bash
curl -s -H "Authorization: Bearer <YOUR_MATRIX_ACCESS_TOKEN>" \
  https://matrix.example.com/_matrix/client/v3/voip/turnServer | jq .
```

Expected response:
```json
{
  "username": "<generated>",
  "password": "<generated>",
  "uris": [
    "turn:turn.cloudflare.com:3478?transport=udp",
    "turn:turn.cloudflare.com:3478?transport=tcp",
    "turns:turn.cloudflare.com:5349?transport=tcp",
    "turns:turn.cloudflare.com:443?transport=tcp"
  ],
  "ttl": 86400
}
```

**Step 2: Test with invalid token**

```bash
curl -s -H "Authorization: Bearer invalid_token_here" \
  https://matrix.example.com/_matrix/client/v3/voip/turnServer
```

Expected: 401 Unauthorized (matrix-turnify forwards Synapse's rejection).

**Step 3: Test a real 1:1 call**

1. Open Element on two devices/accounts
2. Start a direct message between them
3. Click the phone icon (voice call) or camera icon (video call)
4. Verify the call connects

**Step 4: Verify TURN is being used (optional)**

In Element Web, open DevTools (F12) > Network tab. Look for requests to `turn.cloudflare.com`. You can also check `chrome://webrtc-internals` during a call to see ICE candidates using Cloudflare TURN.

**Step 5: Check matrix-turnify logs for credential generation**

```bash
docker logs matrix-turnify --tail 20
```

Expected: Log entries showing successful credential generation.

**Step 6: Commit Phase 1 config changes**

```bash
git add docker-compose.yml .env
git commit -m "feat: add Cloudflare TURN via matrix-turnify for 1:1 VoIP calls"
```

---

## Phase 2: LiveKit + Element Call (Group Calls)

### Task 6: Generate LiveKit API Keys

**Step 1: Generate a LiveKit API key and secret**

```bash
# Generate a random API secret (32+ characters)
openssl rand -base64 32
```

Save two values:
- `LIVEKIT_API_KEY`: Choose a name like `matrixrtc` (alphanumeric, no spaces)
- `LIVEKIT_API_SECRET`: The random string from openssl

**Step 2: Add to your .env file**

```bash
LIVEKIT_API_KEY=matrixrtc
LIVEKIT_API_SECRET=<your-generated-secret>
LIVEKIT_HOST=lk.example.com  # subdomain you'll use for LiveKit
```

---

### Task 7: Create LiveKit Configuration File

**Files:**
- Create: `livekit.yaml` (in your Matrix deployment directory, alongside docker-compose.yml)

**Step 1: Create the config file**

```yaml
# livekit.yaml — LiveKit SFU configuration for MatrixRTC
port: 7880
bind_addresses:
  - "0.0.0.0"

rtc:
  tcp_port: 7881
  port_range_start: 50100
  port_range_end: 50200
  use_external_ip: true

room:
  auto_create: false

logging:
  level: info

keys:
  matrixrtc: "${LIVEKIT_API_SECRET}"  # must match LIVEKIT_API_KEY
```

Notes:
- `use_external_ip: true` — LiveKit will auto-detect your public IP for ICE candidates
- `auto_create: false` — rooms are created by lk-jwt-service, not by arbitrary connections
- `port_range_start/end` — narrowed to 100 ports; adjust wider if you expect many concurrent calls
- The key name (`matrixrtc`) must match the `LIVEKIT_API_KEY` value

---

### Task 8: Deploy LiveKit SFU + lk-jwt-service

**Files:**
- Modify: Your `docker-compose.yml`

**Step 1: Add LiveKit and lk-jwt-service to docker-compose.yml**

```yaml
  livekit:
    image: livekit/livekit-server:latest
    container_name: livekit
    command: --config /etc/livekit.yaml
    network_mode: host  # required for WebRTC UDP on Linux
    volumes:
      - ./livekit.yaml:/etc/livekit.yaml:ro
    environment:
      - LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}
    restart: unless-stopped

  lk-jwt-service:
    image: ghcr.io/element-hq/lk-jwt-service:latest
    container_name: lk-jwt-service
    environment:
      - LIVEKIT_URL=wss://${LIVEKIT_HOST}
      - LIVEKIT_KEY=${LIVEKIT_API_KEY}
      - LIVEKIT_SECRET=${LIVEKIT_API_SECRET}
      - LIVEKIT_FULL_ACCESS_HOMESERVERS=example.com  # replace with your Matrix domain
      - LIVEKIT_JWT_PORT=8080
    restart: unless-stopped
    depends_on:
      - livekit
```

Important notes:
- LiveKit uses `network_mode: host` because it needs direct UDP access. This means it binds directly to the host's network interfaces (no Docker port mapping needed).
- `LIVEKIT_URL` uses `wss://` — this is the WebSocket URL clients connect to.
- `LIVEKIT_FULL_ACCESS_HOMESERVERS` should be your Matrix domain (e.g., `example.com`). This controls which homeserver's users can create rooms. Federated users can still join.
- lk-jwt-service does NOT need host networking — it's HTTP only.

**Step 2: Pull and start the containers**

```bash
docker compose pull livekit lk-jwt-service
docker compose up -d livekit lk-jwt-service
```

**Step 3: Verify both containers are running**

```bash
docker logs livekit --tail 10
docker logs lk-jwt-service --tail 10
```

Expected: LiveKit shows "starting LiveKit server" with no errors. lk-jwt-service shows it's listening on port 8080.

---

### Task 9: Configure DNS and Firewall for LiveKit

**Step 1: Create DNS record for LiveKit subdomain**

Add an A record in your DNS provider:

```
lk.example.com    A    <your-server-public-IP>
```

**Do NOT proxy this through Cloudflare** (set to DNS-only / grey cloud). LiveKit needs direct connections for WebRTC.

**Step 2: Open firewall ports**

```bash
# LiveKit signaling (WebSocket)
sudo ufw allow 7880/tcp

# LiveKit WebRTC over TCP (fallback)
sudo ufw allow 7881/tcp

# LiveKit WebRTC media (UDP)
sudo ufw allow 50100:50200/udp
```

Adjust the firewall commands if you use `iptables`, `firewalld`, or a cloud provider's security group.

**Step 3: Set up TLS for LiveKit**

LiveKit's WebSocket endpoint needs TLS (`wss://`). Options:

**Option A: Caddy as a TLS reverse proxy (recommended)**

```caddyfile
lk.example.com {
    reverse_proxy localhost:7880
}
```

Caddy auto-provisions Let's Encrypt certificates.

**Option B: nginx with certbot**

```nginx
server {
    listen 443 ssl;
    server_name lk.example.com;

    ssl_certificate /etc/letsencrypt/live/lk.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lk.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:7880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

---

### Task 10: Route lk-jwt-service Through Cloudflare Tunnel

**Files:**
- Modify: Your `cloudflared` config file

**Step 1: Add the JWT service route to your tunnel config**

The lk-jwt-service exposes an HTTP endpoint at `/sfu/get` that clients call to get JWTs. Route this through your existing Cloudflare Tunnel.

Update your `cloudflared` config:

```yaml
tunnel: <your-tunnel-id>
credentials-file: /path/to/credentials.json

ingress:
  # TURN credential requests → matrix-turnify
  - hostname: matrix.example.com
    path: ".*voip/turnServer$"
    service: http://matrix-turnify:4499

  # NEW: MatrixRTC JWT service
  - hostname: matrixrtc.example.com
    service: http://lk-jwt-service:8080

  # Synapse catch-all
  - hostname: matrix.example.com
    service: http://synapse:8008

  # Required catch-all
  - service: http_status:404
```

Alternatively, if you want to use a path prefix on the same hostname instead of a subdomain:

```yaml
  # MatrixRTC JWT service (path-based on same hostname)
  - hostname: matrix.example.com
    path: "^/sfu/"
    service: http://lk-jwt-service:8080
```

**Step 2: Add DNS for the MatrixRTC subdomain (if using subdomain approach)**

In Cloudflare DNS, add a CNAME pointing to your tunnel:

```
matrixrtc.example.com    CNAME    <your-tunnel-id>.cfargotunnel.com
```

This one CAN be proxied through Cloudflare (orange cloud) since it's HTTP only.

**Step 3: Restart cloudflared**

```bash
sudo systemctl restart cloudflared
# or: docker compose restart cloudflared
```

---

### Task 11: Configure Synapse for MatrixRTC

**Files:**
- Modify: Your Synapse `homeserver.yaml`
- Modify: Your `.well-known/matrix/client` response

**Step 1: Enable required experimental features in homeserver.yaml**

Add or update in `homeserver.yaml`:

```yaml
experimental_features:
  msc3266_enabled: true   # Room summary API
  msc4222_enabled: true   # Adding `state_after` to sync v2
  msc4140_enabled: true   # Delayed events for MatrixRTC

max_event_delay_duration: 24h

rc_delayed_event_mgmt:
  per_second: 1
  burst_count: 20
```

**Step 2: Update .well-known/matrix/client**

Your Matrix client well-known response must advertise the LiveKit transport. Update whatever serves `https://example.com/.well-known/matrix/client`:

```json
{
  "m.homeserver": {
    "base_url": "https://matrix.example.com"
  },
  "org.matrix.msc4143.rtc_foci": [
    {
      "type": "livekit",
      "livekit_service_url": "https://matrixrtc.example.com"
    }
  ]
}
```

If using path-based routing instead of subdomain:

```json
{
  "m.homeserver": {
    "base_url": "https://matrix.example.com"
  },
  "org.matrix.msc4143.rtc_foci": [
    {
      "type": "livekit",
      "livekit_service_url": "https://matrix.example.com"
    }
  ]
}
```

Ensure the well-known response has the CORS header:
```
Access-Control-Allow-Origin: *
```

**Step 3: Restart Synapse**

```bash
docker compose restart synapse
```

---

### Task 12: Test Phase 2 — Group Calls

**Step 1: Verify the well-known endpoint**

```bash
curl -s https://example.com/.well-known/matrix/client | jq .
```

Expected: JSON with `org.matrix.msc4143.rtc_foci` containing `livekit_service_url`.

**Step 2: Verify the JWT service is reachable**

```bash
curl -s https://matrixrtc.example.com/healthz
```

Expected: 200 OK or similar health response.

**Step 3: Test a group call**

1. Open Element Web or Element X on 2-3 devices/accounts
2. Create a group room (or use an existing one)
3. Click the video call button
4. All participants should see each other

**Step 4: Test screen sharing**

1. During a group call, click the screen share button
2. Select a screen/window/tab
3. Other participants should see your shared screen

**Step 5: Check logs if calls fail**

```bash
docker logs livekit --tail 30
docker logs lk-jwt-service --tail 30
docker logs matrix-turnify --tail 30
docker logs synapse --tail 30 2>&1 | grep -i rtc
```

Common issues:
- `lk-jwt-service` returning 403 → check `LIVEKIT_FULL_ACCESS_HOMESERVERS` matches your domain
- LiveKit WebSocket unreachable → check DNS, TLS, and firewall ports
- "Waiting for media" forever → check UDP ports (50100-50200) are open
- Well-known not served with CORS → add `Access-Control-Allow-Origin: *` header

**Step 6: Use testmatrix tool for diagnostics (optional)**

Visit https://codeberg.org/spaetz/testmatrix/ for a community diagnostic tool that validates JWT and call connection.

**Step 7: Commit Phase 2 config changes**

```bash
git add docker-compose.yml livekit.yaml
git commit -m "feat: add LiveKit SFU + lk-jwt-service for MatrixRTC group calls"
```

---

## Final Architecture Summary

After both phases, your stack looks like:

```
Element Clients
    |
    v
Cloudflare Tunnel (cloudflared)
    |-- .*voip/turnServer    --> matrix-turnify (:4499)  --> Cloudflare TURN API
    |-- matrixrtc.*          --> lk-jwt-service (:8080)
    |-- everything else      --> Synapse (:8008)

LiveKit SFU (direct, host network)
    |-- :7880 TCP (WSS via Caddy/nginx)
    |-- :7881 TCP (WebRTC TCP fallback)
    |-- :50100-50200 UDP (WebRTC media)

DNS:
    matrix.example.com       --> Cloudflare Tunnel (proxied)
    matrixrtc.example.com    --> Cloudflare Tunnel (proxied, JWT only)
    lk.example.com           --> Server IP direct (DNS-only, no CF proxy)
```

## References

- Design: `docs/plans/2026-02-15-cloudflare-voip-design.md`
- Research: `docs/cloudflare-voip/` (6 files)
- [matrix-turnify](https://github.com/bpbradley/matrix-turnify)
- [LiveKit self-hosting](https://docs.livekit.io/transport/self-hosting/vm/)
- [lk-jwt-service](https://github.com/element-hq/lk-jwt-service)
- [Element Call backend deployment guide](https://willlewis.co.uk/blog/posts/deploy-element-call-backend-with-synapse-and-docker-compose/)
- [Cloudflare Tunnel ingress rules](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/)
- [Synapse TURN configuration](https://element-hq.github.io/synapse/latest/turn-howto.html)
- [MatrixRTC configuration (Element docs)](https://docs.element.io/latest/element-server-suite-pro/configuring-components/configuring-matrix-rtc/)
