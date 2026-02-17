# Matrix E2EE Encryption Enforcement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce E2EE encryption by default for all new rooms on matrix.apehost.net via three layers: Synapse server config, Element Web client config, and well-known policy.

**Architecture:** Three independent config changes — server-side enforcement in homeserver.yaml, client default in element-config.json, and a well-known endpoint served by Caddy. No code, only configuration. Changes require container restarts.

**Tech Stack:** Synapse (homeserver.yaml), Element Web (config.json), Caddy (Caddyfile), Docker Compose. All files on melmbox (192.168.30.50) via SSH.

**Design doc:** `docs/plans/2026-02-16-matrix-encryption-enforcement-design.md`

---

### Task 1: Add encryption enforcement to homeserver.yaml

**Files:**
- Modify: `/opt/stacks/matrix-synapse/data/homeserver.yaml` (on melmbox)

**Step 1: Verify current state**

Run:
```bash
ssh melmbox "grep -c 'encryption_enabled_by_default' /opt/stacks/matrix-synapse/data/homeserver.yaml"
```
Expected: `0` (not yet configured)

**Step 2: Append encryption config**

Run:
```bash
ssh melmbox "sudo tee -a /opt/stacks/matrix-synapse/data/homeserver.yaml > /dev/null << 'EOF'

# E2EE enforcement — all new rooms created on this server are encrypted by default
encryption_enabled_by_default_for_room_type: \"all\"
EOF"
```

**Step 3: Verify the config was appended**

Run:
```bash
ssh melmbox "grep 'encryption_enabled_by_default' /opt/stacks/matrix-synapse/data/homeserver.yaml"
```
Expected: `encryption_enabled_by_default_for_room_type: "all"`

**Step 4: Restart Synapse and verify it starts cleanly**

Run:
```bash
ssh melmbox "sudo docker restart synapse && sleep 20 && docker ps --filter 'name=^/synapse$' --format '{{.Status}}'"
```
Expected: `Up XX seconds (healthy)`

If Synapse fails to start, check logs: `ssh melmbox "docker logs synapse --tail 30"`

---

### Task 2: Add E2EE default to element-config.json

**Files:**
- Modify: `/opt/stacks/matrix-synapse/element-config.json` (on melmbox)

**Step 1: Add io.element.e2ee to the config**

Run:
```bash
ssh melmbox "sudo python3 -c \"
import json
with open('/opt/stacks/matrix-synapse/element-config.json', 'r') as f:
    config = json.load(f)

config['default_server_config']['io.element.e2ee'] = {
    'default': True
}

with open('/opt/stacks/matrix-synapse/element-config.json', 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
\""
```

**Step 2: Verify the config**

Run:
```bash
ssh melmbox "python3 -c \"import json; c=json.load(open('/opt/stacks/matrix-synapse/element-config.json')); print(json.dumps(c['default_server_config'].get('io.element.e2ee'), indent=2))\""
```
Expected:
```json
{
  "default": true
}
```

**Step 3: Restart Element Web**

Run:
```bash
ssh melmbox "sudo docker restart element-web && sleep 5 && docker ps --filter 'name=^/element-web$' --format '{{.Status}}'"
```
Expected: `Up X seconds (healthy)`

---

### Task 3: Create well-known static JSON file

**Files:**
- Create: `/opt/stacks/matrix-synapse/well-known-matrix-client.json` (on melmbox)

**Step 1: Create the well-known JSON file**

Run:
```bash
ssh melmbox "sudo tee /opt/stacks/matrix-synapse/well-known-matrix-client.json > /dev/null << 'EOF'
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
EOF"
```

**Step 2: Verify the file is valid JSON**

Run:
```bash
ssh melmbox "python3 -m json.tool /opt/stacks/matrix-synapse/well-known-matrix-client.json > /dev/null && echo 'Valid JSON'"
```
Expected: `Valid JSON`

---

### Task 4: Add well-known route to Caddyfile

**Files:**
- Modify: `/opt/stacks/matrix-synapse/Caddyfile` (on melmbox)

**Step 1: Write updated Caddyfile with well-known route**

The well-known route must come BEFORE the Synapse catch-all `handle` block. We inline the JSON using Caddy's `respond` with backtick-delimited body. We also mount the JSON file and use `file` directive instead for maintainability.

Run:
```bash
ssh melmbox "sudo tee /opt/stacks/matrix-synapse/Caddyfile > /dev/null << 'CADDYEOF'
# Caddy reverse proxy for Matrix Synapse + VoIP services
# Listens on :8443 (HTTP, not TLS — Cloudflare Tunnel handles TLS)
# SPOF for all Matrix traffic — healthcheck in compose.yaml monitors availability

:8443 {
    log {
        output file /var/log/caddy/access.log {
            roll_size 10mb
            roll_keep 3
        }
        format json
    }

    # Serve well-known for Matrix client discovery + E2EE policy
    @wellknown path /.well-known/matrix/client
    handle @wellknown {
        header Content-Type \"application/json\"
        header Access-Control-Allow-Origin \"*\"
        root * /srv
        rewrite * /well-known-matrix-client.json
        file_server
    }

    # Route TURN credential requests to matrix-turnify
    @turnify path_regexp turnify /_matrix/client/(api/v1|r0|v3|unstable)/voip/turnServer
    handle @turnify {
        reverse_proxy matrix-turnify:4499
    }

    # Route MatrixRTC JWT requests to lk-jwt-service
    @sfu path /sfu/get
    handle @sfu {
        reverse_proxy lk-jwt-service:8080
    }

    # Everything else goes to Synapse
    handle {
        reverse_proxy synapse:8008
    }
}
CADDYEOF"
```

**Step 2: Verify Caddyfile content**

Run:
```bash
ssh melmbox "grep -A5 'wellknown' /opt/stacks/matrix-synapse/Caddyfile"
```
Expected: Shows the `@wellknown` matcher and handler block with CORS headers.

---

### Task 5: Mount well-known file into Caddy container

**Files:**
- Modify: `/etc/komodo/stacks/matrix-synapse/compose.yaml` (on melmbox)

**Step 1: Add the volume mount to caddy-matrix**

Add `/opt/stacks/matrix-synapse/well-known-matrix-client.json:/srv/well-known-matrix-client.json:ro` to the caddy-matrix volumes.

Run:
```bash
ssh melmbox "sudo sed -i '/Caddyfile:\/etc\/caddy\/Caddyfile:ro/a\      - /opt/stacks/matrix-synapse/well-known-matrix-client.json:/srv/well-known-matrix-client.json:ro' /etc/komodo/stacks/matrix-synapse/compose.yaml"
```

**Step 2: Verify the mount was added**

Run:
```bash
ssh melmbox "grep -A3 'Caddyfile' /etc/komodo/stacks/matrix-synapse/compose.yaml | head -4"
```
Expected:
```
      - /opt/stacks/matrix-synapse/Caddyfile:/etc/caddy/Caddyfile:ro
      - /opt/stacks/matrix-synapse/well-known-matrix-client.json:/srv/well-known-matrix-client.json:ro
```

**Step 3: Recreate Caddy container with new mount**

Run:
```bash
ssh melmbox "cd /etc/komodo/stacks/matrix-synapse && sudo docker compose up -d caddy-matrix"
```
Expected: `Container caddy-matrix  Recreated` and `Started`

---

### Task 6: Verify all three layers

**Step 1: Verify well-known endpoint via tunnel**

Run:
```bash
curl -s https://matrix.apehost.net/.well-known/matrix/client | python3 -m json.tool
```
Expected: JSON with `m.homeserver`, `org.matrix.msc4143.rtc_foci`, and `io.element.e2ee.default: true`

**Step 2: Verify CORS header on well-known**

Run:
```bash
curl -s -I https://matrix.apehost.net/.well-known/matrix/client | grep -i 'access-control\|content-type'
```
Expected:
```
Content-Type: application/json
Access-Control-Allow-Origin: *
```

**Step 3: Verify Synapse still works through Caddy**

Run:
```bash
curl -s -o /dev/null -w '%{http_code}' https://matrix.apehost.net/_matrix/client/v3/login
```
Expected: `200`

**Step 4: Verify TURN and SFU endpoints still work**

Run:
```bash
curl -s -o /dev/null -w '%{http_code}' https://matrix.apehost.net/_matrix/client/v3/voip/turnServer -H 'Authorization: Bearer invalid'
curl -s -o /dev/null -w '%{http_code}' -X POST https://matrix.apehost.net/sfu/get -H 'Content-Type: application/json' -d '{}'
```
Expected: `401` and `400`

**Step 5: Run full smoke test**

Run:
```bash
ssh melmbox "bash /opt/stacks/matrix-synapse/smoke-test.sh"
```
Expected: All tests pass, 0 failures.

---

### Task 7: Update smoke test with well-known check

**Files:**
- Modify: `/opt/stacks/matrix-synapse/smoke-test.sh` (on melmbox)

**Step 1: Add well-known test to smoke-test.sh**

Add a new section after the SFU tests that verifies:
- `GET /.well-known/matrix/client` returns 200
- Response contains `io.element.e2ee`
- Response contains `Access-Control-Allow-Origin: *` header

**Step 2: Run updated smoke test**

Run:
```bash
ssh melmbox "bash /opt/stacks/matrix-synapse/smoke-test.sh"
```
Expected: All tests pass including new well-known checks.

---

### Task 8: Update documentation

**Files:**
- Modify: `docs/cloudflare-voip/07-deployment-guide.md`
- Modify: `docs/cloudflare-voip/README.md`

**Step 1: Add encryption section to deployment guide**

Add a new section documenting:
- The three enforcement layers and what each does
- How to verify encryption is enforced
- How to change the policy if needed

**Step 2: Update README status table**

Add encryption enforcement as a completed item.
