#!/bin/bash
# 批量音频转文本自动化脚本 (STT)
# 管理 Tunnel、HTTP 服务器和批量处理

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUNNEL_LOG="/tmp/stt_tunnel_$$.log"
HTTP_PORT=8890
TUNNEL_URL=""

# 清理函数
cleanup() {
    echo ""
    echo "🧹 清理进程..."
    pkill -9 -f "cloudflared.*http://localhost:$HTTP_PORT" 2>/dev/null || true
    pkill -9 -f "http.server $HTTP_PORT" 2>/dev/null || true
    rm -f "$TUNNEL_LOG"
}

trap cleanup EXIT

# 启动 HTTP 服务器
start_http_server() {
    echo "🚀 启动 HTTP 服务器 (端口 $HTTP_PORT)..."
    cd "$SCRIPT_DIR/00_audio_splits"
    python3 -m http.server $HTTP_PORT > /dev/null 2>&1 &
    HTTP_PID=$!
    echo "   HTTP Server PID: $HTTP_PID"
    sleep 3
}

# 启动 Cloudflare Tunnel
start_tunnel() {
    echo "🌐 启动 Cloudflare Tunnel..."
    ~/.local/bin/cloudflared tunnel --url "http://localhost:$HTTP_PORT" > "$TUNNEL_LOG" 2>&1 &
    TUNNEL_PID=$!
    echo "   Tunnel PID: $TUNNEL_PID"
    
    # 等待获取 URL
    echo "   等待 tunnel 就绪..."
    for i in {1..60}; do
        TUNNEL_URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" "$TUNNEL_LOG" 2>/dev/null | head -1)
        if [ -n "$TUNNEL_URL" ]; then
            echo "   ✅ Tunnel URL: $TUNNEL_URL"
            return 0
        fi
        sleep 1
    done
    
    echo "   ❌ 获取 Tunnel URL 超时"
    cat "$TUNNEL_LOG"
    return 1
}

# 验证 tunnel 可访问
verify_tunnel() {
    echo "🔍 验证 tunnel 可访问性..."
    local test_url="${TUNNEL_URL}/"
    
    # 先等待一段时间让 tunnel 完全就绪
    echo "   等待 tunnel 稳定 (15秒)..."
    sleep 15
    
    for i in {1..15}; do
        if curl -s --max-time 15 "$test_url" > /dev/null 2>&1; then
            echo "   ✅ Tunnel 可访问"
            return 0
        fi
        echo "   等待中... ($i/15)"
        sleep 3
    done
    
    echo "   ⚠️ Tunnel 验证超时，继续尝试..."
    return 0
}

# 运行批量处理
run_batch_process() {
    echo ""
    echo "🎙️  开始批量音频转文本处理..."
    echo "   Input: 00_audio_splits"
    echo "   Output: 01_stt"
    echo "   Tunnel: $TUNNEL_URL"
    echo ""
    
    cd "$SCRIPT_DIR"
    
    # 运行批量处理
    uv run python batch_stt.py "$TUNNEL_URL" --input 00_audio_splits --output 01_stt
}

# 主流程
main() {
    echo "=========================================="
    echo "  批量音频转文本 (STT) - 自动化处理"
    echo "=========================================="
    echo ""
    
    # 检查依赖
    if [ ! -f "$SCRIPT_DIR/.venv/bin/python" ]; then
        echo "❌ 未找到 Python 虚拟环境"
        exit 1
    fi
    
    if [ ! -f "$HOME/.local/bin/cloudflared" ]; then
        echo "❌ 未找到 cloudflared"
        exit 1
    fi
    
    # 检查输入目录
    if [ ! -d "$SCRIPT_DIR/00_audio_splits" ]; then
        echo "❌ 输入目录不存在: 00_audio_splits"
        exit 1
    fi
    
    FILE_COUNT=$(find "$SCRIPT_DIR/00_audio_splits" -name "*.mp3" | wc -l)
    echo "📁 找到 $FILE_COUNT 个 MP3 文件"
    
    # 检查已处理数量
    PROCESSED_COUNT=$(ls "$SCRIPT_DIR/01_stt" -R 2>/dev/null | grep -c "\.txt$" || echo "0")
    echo "📄 已有 $PROCESSED_COUNT 个文本文件"
    echo ""
    
    # 启动服务
    start_http_server
    start_tunnel
    verify_tunnel
    
    # 运行处理
    run_batch_process
    
    echo ""
    echo "=========================================="
    echo "  ✅ 处理完成！"
    echo "=========================================="
}

main "$@"
