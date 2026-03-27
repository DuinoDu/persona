# 02_transcripts to 03_parts

ai="codex exec --dangerously-bypass-approvals-and-sandbox"
# ai="aiden --permission-mode agentFull --one-shot"
# ai="traecli --yolo --print"
skip=0

data_1="data/02_transcripts/曲曲2024（全）" # done
data_2="data/03_parts/曲曲2024（全）" # done

echo "
${data_1}下有多个json文件(不考虑递归，只考虑这个路径下一级目录)，是原始转录文件
跳过前${skip}个json文件，对后面的每个文件
依次用tmux运行 
cd /home/duino/ws/ququ/ppl && export AI='${ai}' export JSON_FILE=<json_file_path> export PARTS_FOLDER=${data_2} bash -lc '${ai} \$(bash claw/sop/ash fix_parts_inner.sh)'
每个tmux任务运行的超时设置为60分钟
同时运行最多不超过4个tmux任务
需要每个10分钟，检查tmux session的运行状态(并主动报告状态)，如果异常，则kill，retry
"

# # Test prompt.sh
# process() {
#     export AI="aiden --one-shot" && export JSON_FILE="$1" PARTS_FOLDER="$data_2" && aiden --permission-mode agentFull "$(bash claw/sop/fix_parts_inner.sh)"
# }
# process '50 - 曲曲直播 2024年08月09日 曲曲大女人 美人解忧铺 #曲曲麦肯锡.json'
