#!/bin/bash

# 批量语音转文本脚本
# 处理 00_audio_splits 下所有 mp3 文件，保留文件夹结构

set -e

# 配置
INPUT_DIR="/home/duino/ws/ququ/process_youtube/00_audio_splits"
OUTPUT_DIR="/home/duino/ws/ququ/process_youtube/02_processed_local"
SCRIPT_DIR="/home/duino/ws/ququ/process_youtube/speech2text"
LOG_FILE="/home/duino/ws/ququ/process_youtube/batch_transcribe.log"

# HuggingFace Token
export HF_TOKEN="${HF_TOKEN:-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}"

# 说话人名称
SPEAKERS="主持人,嘉宾"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo -e "$msg"
    echo "$msg" >> "$LOG_FILE"
}

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 统计
total=0
success=0
failed=0
skipped=0

# 获取所有 mp3 文件
mapfile -t files < <(find "$INPUT_DIR" -name "*.mp3" -type f | sort)
total=${#files[@]}

log "=========================================="
log "开始批量转录"
log "输入目录: $INPUT_DIR"
log "输出目录: $OUTPUT_DIR"
log "总文件数: $total"
log "=========================================="

for i in "${!files[@]}"; do
    input_file="${files[$i]}"

    # 计算相对路径
    rel_path="${input_file#$INPUT_DIR/}"
    rel_dir=$(dirname "$rel_path")
    base_name=$(basename "$input_file" .mp3)

    # 创建输出目录
    output_subdir="$OUTPUT_DIR/$rel_dir/$base_name"

    # 检查是否已处理（如果 txt 文件存在则跳过）
    if [[ -f "$output_subdir/$base_name.txt" ]]; then
        log "${YELLOW}[$((i+1))/$total] 跳过 (已存在): $rel_path${NC}"
        ((skipped++))
        continue
    fi

    mkdir -p "$output_subdir"

    log "${GREEN}[$((i+1))/$total] 处理: $rel_path${NC}"

    # 创建临时目录
    temp_dir=$(mktemp -d)

    # 运行转录（同时输出到终端和日志）
    if cd "$SCRIPT_DIR" && uv run transcribe "$input_file" -s "$SPEAKERS" -f all -o "$temp_dir" 2>&1 | tee -a "$LOG_FILE"; then
        # 移动输出文件到目标目录
        for ext in txt srt json; do
            if [[ -f "$temp_dir/$base_name.$ext" ]]; then
                mv "$temp_dir/$base_name.$ext" "$output_subdir/$base_name.$ext"
            fi
        done
        log "${GREEN}  ✓ 完成${NC}"
        ((success++))
    else
        log "${RED}  ✗ 失败${NC}"
        ((failed++))
        # 记录失败的文件
        echo "$input_file" >> "$OUTPUT_DIR/failed_files.txt"
    fi

    # 清理临时目录
    rm -rf "$temp_dir"
done

log "=========================================="
log "批量转录完成"
log "成功: $success"
log "失败: $failed"
log "跳过: $skipped"
log "总计: $total"
log "=========================================="

if [[ $failed -gt 0 ]]; then
    log "${YELLOW}失败文件列表: $OUTPUT_DIR/failed_files.txt${NC}"
fi
