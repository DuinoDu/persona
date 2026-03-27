# 02_transcripts to 03_parts

# ai="codex exec --dangerously-bypass-approvals-and-sandbox"
ai="aiden --permission-mode agentFull --one-shot"
# ai="traecli --yolo --print"

skip=0

# data="data/03_transcripts/曲曲2023（全）"   # done
# data="data/03_transcripts/曲曲2022"       # done
data="data/03_transcripts/曲曲2024（全）" # done
# data="data/03_transcripts/曲曲2025（全）" # done
# data="data/03_transcripts/曲曲2026"       # done

echo "
${data}下有多个json文件(不考虑递归，只考虑这个路径下一级目录)，
跳过前${skip}个json文件，对后面的每个文件，先判断这个json文件是不是已经处理了，如果已经处理了，就跳过处理下一个json
依次用tmux运行 
cd /home/duino/ws/ququ/ppl && export AI='${ai}' export JSON_FILE=<json_file_path> bash -lc '${ai} \$(bash transcripts_to_parts_inner.sh)'
每个tmux任务运行的超时设置为60分钟
同时运行最多不超过4个tmux任务
需要每个10分钟，检查tmux session的运行状态(并主动报告状态)，如果异常，则kill，retry
"

# Test prompt.sh
process() {
    export AI="aiden --one-shot" && export JSON_FILE="$1" && aiden --permission-mode agentFull "$(bash transcripts_to_parts_inner.sh)"
}
# process '043 - 曲曲大女人 2023年04月13日 高清分章节完整版  #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺.json'
