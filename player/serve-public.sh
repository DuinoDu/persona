#!/bin/bash
# Serve via Cloudflare Tunnel.

set -euo pipefail

SERVE_PORT=10927

HTTP_LOG="/tmp/mp3_http_${SERVE_PORT}.log"
TUNNEL_LOG="/tmp/mp3_tunnel_${SERVE_PORT}.log"
HTTP_PID_FILE="/tmp/mp3_http_${SERVE_PORT}.pid"
TUNNEL_PID_FILE="/tmp/mp3_tunnel_${SERVE_PORT}.pid"

cleanup() {
    echo ""
    echo "🧹 Stopping server..."
    if [ -f "$HTTP_PID_FILE" ]; then
        kill "$(cat "$HTTP_PID_FILE")" >/dev/null 2>&1 || true
        rm -f "$HTTP_PID_FILE"
    fi
    if [ -f "$TUNNEL_PID_FILE" ]; then
        kill "$(cat "$TUNNEL_PID_FILE")" >/dev/null 2>&1 || true
        rm -f "$TUNNEL_PID_FILE"
    fi
    rm -f "$HTTP_LOG" "$TUNNEL_LOG"
}

trap cleanup EXIT INT TERM


if [ ! -x "$HOME/.local/bin/cloudflared" ]; then
    echo "❌ cloudflared not found at $HOME/.local/bin/cloudflared"
    exit 1
fi

echo "🚀 Starting HTTP server on port $SERVE_PORT..."
npm run build
npm run start >"$HTTP_LOG" 2>&1 &
HTTP_PID=$!
echo "$HTTP_PID" > "$HTTP_PID_FILE"

echo "🌐 Starting Cloudflare Tunnel..."
"$HOME/.local/bin/cloudflared" tunnel --protocol http2 --url "http://localhost:$SERVE_PORT" >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!
echo "$TUNNEL_PID" > "$TUNNEL_PID_FILE"

echo "⏳ Waiting for tunnel URL..."
TUNNEL_URL=""
for _ in {1..60}; do
    TUNNEL_URL="$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" "$TUNNEL_LOG" | head -1 || true)"
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
    sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
    echo "❌ Failed to get tunnel URL."
    echo "Log: $TUNNEL_LOG"
    exit 1
fi

echo "✅ Tunnel URL: $TUNNEL_URL"
echo "📝 Logs: $HTTP_LOG , $TUNNEL_LOG"
echo "🛑 Stop: kill $(cat "$HTTP_PID_FILE") $(cat "$TUNNEL_PID_FILE")"

wait
