#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path('/home/duino/ws/ququ/process_youtube')
SRC = ROOT / 'data/03_transcripts/曲曲2024（全）/19 - 曲曲大女人 2024年04月25日 高清分章节完整版 #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺.json'
OUT_DIR = ROOT / 'data/04_conversations_v2/曲曲2024（全）/19 - 曲曲大女人'
RAW_DIR = OUT_DIR / '_raw_sections'
PROMPT_DIR = OUT_DIR / '_prompts'
LOG_DIR = OUT_DIR / '_codex_logs'
SOURCE_FILE_NAME = SRC.name
AUDIO_FILE = ROOT / 'data/01_downloads/曲曲2024（全）/19 - 曲曲大女人 2024年04月25日 高清分章节完整版 #曲曲大女人 #曲曲麦肯锡  #曲曲 #美人解忧铺.mp3'

MANIFEST = [
    {'index': 0, 'title': '00_开场', 'kind': 'opening', 'persona': '开场', 'start': 0.03, 'end': 1190.30},
    {'index': 1, 'title': '01_27岁_海外艺术生博士_连麦', 'kind': 'call', 'persona': '27岁_海外艺术生博士', 'start': 1190.30, 'end': 2043.03},
    {'index': 2, 'title': '02_27岁_海外艺术生博士_评论', 'kind': 'comment', 'persona': '27岁_海外艺术生博士', 'start': 2046.86, 'end': 2652.61},
    {'index': 3, 'title': '03_30岁_北京金融国企_连麦', 'kind': 'call', 'persona': '30岁_北京金融国企', 'start': 2652.61, 'end': 3379.45},
    {'index': 4, 'title': '04_30岁_北京金融国企_评论', 'kind': 'comment', 'persona': '30岁_北京金融国企', 'start': 3381.55, 'end': 3797.10},
    {'index': 5, 'title': '05_38岁_大学老师_地主家傻儿子_连麦', 'kind': 'call', 'persona': '38岁_大学老师_地主家傻儿子', 'start': 3797.10, 'end': 4552.46},
    {'index': 6, 'title': '06_38岁_大学老师_地主家傻儿子_评论', 'kind': 'comment', 'persona': '38岁_大学老师_地主家傻儿子', 'start': 4554.22, 'end': 5183.42},
    {'index': 7, 'title': '07_38岁_非编大学老师_婚恋迷茫_连麦', 'kind': 'call', 'persona': '38岁_非编大学老师_婚恋迷茫', 'start': 5183.42, 'end': 6108.43},
    {'index': 8, 'title': '08_38岁_非编大学老师_婚恋迷茫_评论', 'kind': 'comment', 'persona': '38岁_非编大学老师_婚恋迷茫', 'start': 6109.50, 'end': 6626.96},
    {'index': 9, 'title': '09_28岁_收租_英国留学_连麦', 'kind': 'call', 'persona': '28岁_收租_英国留学', 'start': 6626.96, 'end': 7040.77},
    {'index': 10, 'title': '10_28岁_收租_英国留学_评论', 'kind': 'comment', 'persona': '28岁_收租_英国留学', 'start': 7043.07, 'end': 7273.40},
    {'index': 11, 'title': '11_30岁_英硕_年入100万_IT凤凰男_连麦', 'kind': 'call', 'persona': '30岁_英硕_年入100万_IT凤凰男', 'start': 7273.40, 'end': 7755.79},
    {'index': 12, 'title': '12_30岁_英硕_年入100万_IT凤凰男_评论', 'kind': 'comment', 'persona': '30岁_英硕_年入100万_IT凤凰男', 'start': 7759.00, 'end': 8019.89},
    {'index': 13, 'title': '13_23岁_江苏国企派遣_想留学_连麦', 'kind': 'call', 'persona': '23岁_江苏国企派遣_想留学', 'start': 8019.89, 'end': 8696.49},
    {'index': 14, 'title': '14_23岁_江苏国企派遣_想留学_评论', 'kind': 'comment', 'persona': '23岁_江苏国企派遣_想留学', 'start': 8697.29, 'end': 8943.21},
    {'index': 15, 'title': '15_30岁_法国博士_买办业务_连麦', 'kind': 'call', 'persona': '30岁_法国博士_买办业务', 'start': 8943.21, 'end': 9698.53},
    {'index': 16, 'title': '16_30岁_法国博士_买办业务_评论', 'kind': 'comment', 'persona': '30岁_法国博士_买办业务', 'start': 9700.66, 'end': 9946.85},
    {'index': 17, 'title': '17_23岁_教育学_想出国二硕_连麦', 'kind': 'call', 'persona': '23岁_教育学_想出国二硕', 'start': 9946.85, 'end': 10544.81},
    {'index': 18, 'title': '18_23岁_教育学_想出国二硕_评论', 'kind': 'comment', 'persona': '23岁_教育学_想出国二硕', 'start': 10547.54, 'end': 11101.63},
    {'index': 19, 'title': '19_34岁_创业_动脸_外国前任_连麦', 'kind': 'call', 'persona': '34岁_创业_动脸_外国前任', 'start': 11101.63, 'end': 11701.33},
    {'index': 20, 'title': '20_34岁_创业_动脸_外国前任_评论', 'kind': 'comment', 'persona': '34岁_创业_动脸_外国前任', 'start': 11704.82, 'end': 11912.80},
    {'index': 21, 'title': '21_24岁_欧洲大客户销售_连麦', 'kind': 'call', 'persona': '24岁_欧洲大客户销售', 'start': 11912.80, 'end': 12658.50},
    {'index': 22, 'title': '22_24岁_欧洲大客户销售_评论', 'kind': 'comment', 'persona': '24岁_欧洲大客户销售', 'start': 12662.77, 'end': 12756.31},
    {'index': 23, 'title': '23_34岁_离异有娃_主播_连麦', 'kind': 'call', 'persona': '34岁_离异有娃_主播', 'start': 12756.31, 'end': 13676.23},
    {'index': 24, 'title': '24_34岁_离异有娃_主播_评论', 'kind': 'comment', 'persona': '34岁_离异有娃_主播', 'start': 13678.72, 'end': 13979.58},
]


def ts(seconds: float) -> str:
    total = round(float(seconds), 2)
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = total - h * 3600 - m * 60
    return f'{h:02d}:{m:02d}:{s:05.2f}'


def speaker_ids(kind: str) -> list[str]:
    return ['host', 'guest'] if kind == 'call' else ['host']


def speaker_names(kind: str) -> dict[str, str]:
    return {'host': '曲曲', 'guest': '嘉宾'} if kind == 'call' else {'host': '曲曲'}


def build_raw_sections() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(SRC.read_text(encoding='utf-8'))
    segments = data['segments']
    split_summary = {
        'source_file': SOURCE_FILE_NAME,
        'audio_file': str(AUDIO_FILE),
        'call_count': 12,
        'total_source_segments': len(segments),
        'total_split_segments': 0,
        'parts': [],
    }
    for i, part in enumerate(MANIFEST):
        start = part['start']
        end = part['end']
        part_segments = []
        for seg in segments:
            seg_start = float(seg['start'])
            if i < len(MANIFEST) - 1:
                if start <= seg_start < end:
                    part_segments.append(seg)
            else:
                if start <= seg_start <= end:
                    part_segments.append(seg)
        payload = {
            'meta': {
                'source_file': SOURCE_FILE_NAME,
                'index': part['index'],
                'kind': part['kind'],
                'persona': part['persona'],
                'title': part['title'],
                'start': part['start'],
                'end': part['end'],
                'start_ts': ts(part['start']),
                'end_ts': ts(part['end']),
                'raw_segment_count': len(part_segments),
                'speaker_ids': speaker_ids(part['kind']),
                'speaker_names': speaker_names(part['kind']),
                'sentence_count': 0,
                'notes': 'raw section for codex cleanup',
            },
            'raw_segments': part_segments,
        }
        out = RAW_DIR / f"{part['title']}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        split_summary['parts'].append({
            'file': f"{part['title']}.json",
            'kind': part['kind'],
            'persona': part['persona'],
            'start': part['start'],
            'end': part['end'],
            'start_ts': ts(part['start']),
            'end_ts': ts(part['end']),
            'segments': len(part_segments),
        })
        split_summary['total_split_segments'] += len(part_segments)
    (OUT_DIR / '_split_summary.json').write_text(json.dumps(split_summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_prompt_files() -> None:
    template = '''请继续这个 section 的文本整理任务，但不要在聊天里输出完整 JSON。

输入 raw section：
{raw_path}

输出文件：
{out_path}

任务：
1. 读取该文件中的 `meta` 和 `raw_segments`。
2. 这是一个 `{kind}` 段。{speaker_rule}
3. 如果 raw diarization 混乱，请按语义、问答轮次和上下文纠正说话人。
4. 你需要：
   - 纠正明显 diarization 错分
   - 把 raw_segments 合并为适合播放器显示的句子级 `sentences`
   - 去掉无意义语气词、空白、明显重复、明显截断残片；但不要改变原意
   - 每句保留 `speaker_id`, `speaker_name`, `start`, `end`, `text`
5. `meta` 必须保留并补充/更新：
   - `speaker_ids`: {speaker_ids}; `speaker_names`: {speaker_names}
   - `sentence_count`: 句子条数
   - `notes`: 简短说明是否修正了少量串音/错分/重复
6. 不要输出 `raw_segments`。
7. 时间戳尽量沿用原始边界；一句可以跨多个 raw segment 合并。
8. 中文句子补上基本标点，保留口语语气，不要总结内容。
9. `meta.source_file` 请写原始总文件名：`{source_file}`
10. `meta.title` 保持和当前 section 标题一致：`{title}`
11. 若段首/段尾有被切断的残句，可直接丢弃残句，保证正式文件干净。
12. 直接把最终 JSON 写入输出文件 `{out_path}`。
13. 写完后请你自己重新读取该输出文件，确认：
   - JSON 可解析
   - 含 `meta` 和 `sentences`
   - `meta.sentence_count == len(sentences)`
   - call 段没有除 host/guest 外的 `speaker_id`
   - opening/comment 段只有 host
14. 输出必须严格符合 schema：`data/03_transcripts/formal_output.schema.json`。
15. 你的最终回复只输出一行：DONE {title} N

补充要求：
- 不要保留明显的 ASR 串音叠字；能确定语义时请合并修正为自然中文句子。
- 对于 call 段，优先按问答轮次修正为 host=曲曲、guest=嘉宾；对于 comment/opening 段，只允许 host。
'''
    for part in MANIFEST:
        kind = part['kind']
        prompt = template.format(
            raw_path=str(RAW_DIR / f"{part['title']}.json"),
            out_path=str(OUT_DIR / f"{part['title']}.json"),
            kind=kind,
            speaker_rule=('只允许两个说话人：`host` = 曲曲，`guest` = 嘉宾。' if kind == 'call' else '这是单人段，只允许 `host` = 曲曲。'),
            speaker_ids='["host", "guest"]' if kind == 'call' else '["host"]',
            speaker_names='{"host":"曲曲","guest":"嘉宾"}' if kind == 'call' else '{"host":"曲曲"}',
            source_file=SOURCE_FILE_NAME,
            title=part['title'],
        )
        (PROMPT_DIR / f"{part['title']}.md").write_text(prompt, encoding='utf-8')


def write_runner() -> None:
    runner = OUT_DIR / '_run_one_codex.sh'
    runner.write_text(
        f'''#!/usr/bin/env bash
set -euo pipefail
TITLE="$1"
BASE="{ROOT}"
OUTDIR="{OUT_DIR}"
PROMPT="$OUTDIR/_prompts/${{TITLE}}.md"
OUT="$OUTDIR/${{TITLE}}.json"
STATUS="$OUTDIR/_codex_logs/${{TITLE}}.status.txt"
if [[ ! -f "$PROMPT" ]]; then
  echo "missing prompt: $PROMPT" >&2
  exit 1
fi
rm -f "$STATUS"
codex exec -C "$BASE" --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -o "$STATUS" - < "$PROMPT"
python - <<'PY' "$OUT"
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
obj = json.loads(p.read_text(encoding='utf-8'))
assert 'meta' in obj and 'sentences' in obj
obj['meta']['sentence_count'] = len(obj['sentences'])
kind = obj['meta']['kind']
allowed = {{'opening':{{'host'}}, 'comment':{{'host'}}, 'call':{{'host','guest'}}}}[kind]
for s in obj['sentences']:
    assert s['speaker_id'] in allowed, (kind, s)
    assert isinstance(s['text'], str) and s['text'].strip(), s
    s['speaker_name'] = '嘉宾' if s['speaker_id'] == 'guest' else '曲曲'
obj['meta']['source_file'] = {SOURCE_FILE_NAME!r}
obj['meta']['title'] = p.stem
p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')
print('validated', p.name, 'sentences=', len(obj['sentences']))
PY
''',
        encoding='utf-8',
    )
    runner.chmod(0o755)


def write_manual_read_summary() -> None:
    summary = {
        'source_file': SOURCE_FILE_NAME,
        'audio_file': str(AUDIO_FILE),
        'method': 'full manual read in 10 chunks before sectioning',
        'call_count': 12,
        'call_ranges': [
            {'call_index': 1, 'title': '01_27岁_海外艺术生博士_连麦', 'start': 1190.30, 'end': 2043.03, 'start_ts': ts(1190.30), 'end_ts': ts(2043.03)},
            {'call_index': 2, 'title': '03_30岁_北京金融国企_连麦', 'start': 2652.61, 'end': 3379.45, 'start_ts': ts(2652.61), 'end_ts': ts(3379.45)},
            {'call_index': 3, 'title': '05_38岁_大学老师_地主家傻儿子_连麦', 'start': 3797.10, 'end': 4552.46, 'start_ts': ts(3797.10), 'end_ts': ts(4552.46)},
            {'call_index': 4, 'title': '07_38岁_非编大学老师_婚恋迷茫_连麦', 'start': 5183.42, 'end': 6108.43, 'start_ts': ts(5183.42), 'end_ts': ts(6108.43)},
            {'call_index': 5, 'title': '09_28岁_收租_英国留学_连麦', 'start': 6626.96, 'end': 7040.77, 'start_ts': ts(6626.96), 'end_ts': ts(7040.77)},
            {'call_index': 6, 'title': '11_30岁_英硕_年入100万_IT凤凰男_连麦', 'start': 7273.40, 'end': 7755.79, 'start_ts': ts(7273.40), 'end_ts': ts(7755.79)},
            {'call_index': 7, 'title': '13_23岁_江苏国企派遣_想留学_连麦', 'start': 8019.89, 'end': 8696.49, 'start_ts': ts(8019.89), 'end_ts': ts(8696.49)},
            {'call_index': 8, 'title': '15_30岁_法国博士_买办业务_连麦', 'start': 8943.21, 'end': 9698.53, 'start_ts': ts(8943.21), 'end_ts': ts(9698.53)},
            {'call_index': 9, 'title': '17_23岁_教育学_想出国二硕_连麦', 'start': 9946.85, 'end': 10544.81, 'start_ts': ts(9946.85), 'end_ts': ts(10544.81)},
            {'call_index': 10, 'title': '19_34岁_创业_动脸_外国前任_连麦', 'start': 11101.63, 'end': 11701.33, 'start_ts': ts(11101.63), 'end_ts': ts(11701.33)},
            {'call_index': 11, 'title': '21_24岁_欧洲大客户销售_连麦', 'start': 11912.80, 'end': 12658.50, 'start_ts': ts(11912.80), 'end_ts': ts(12658.50)},
            {'call_index': 12, 'title': '23_34岁_离异有娃_主播_连麦', 'start': 12756.31, 'end': 13676.23, 'start_ts': ts(12756.31), 'end_ts': ts(13676.23)},
        ],
    }
    (OUT_DIR / '_manual_read_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    build_raw_sections()
    write_prompt_files()
    write_runner()
    write_manual_read_summary()
    print('prepared_sections', len(MANIFEST))
    print('out_dir', OUT_DIR)


if __name__ == '__main__':
    main()
