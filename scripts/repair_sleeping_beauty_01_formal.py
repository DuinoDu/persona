#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path('/home/duino/ws/ququ/process_youtube')
SRC = ROOT / 'data/03_transcripts/曲曲2025（全）/01 - 睡美人2025年第一場直播 臥播主打就是鬆弛感 2025年1月2日 ｜ 曲曲麥肯錫.json'
OUT_DIR = ROOT / 'data/03_transcripts/曲曲2025（全）/01'
RAW_DIR = OUT_DIR / '_raw_sections'
PROMPT_DIR = OUT_DIR / '_prompts'
LOG_DIR = OUT_DIR / '_codex_logs'
SOURCE_FILE_NAME = SRC.name

MANIFEST = [
    {'index': 0, 'title': '00_开场', 'kind': 'opening', 'persona': '开场', 'start': 0.03, 'end': 707.26},
    {'index': 1, 'title': '01_39岁医学博士短婚无娃_连麦', 'kind': 'call', 'persona': '39岁医学博士短婚无娃', 'start': 707.63, 'end': 1344.13},
    {'index': 2, 'title': '02_39岁医学博士短婚无娃_评论', 'kind': 'comment', 'persona': '39岁医学博士短婚无娃', 'start': 1349.56, 'end': 1583.88},
    {'index': 3, 'title': '03_98年美国理工博士_连麦', 'kind': 'call', 'persona': '98年美国理工博士', 'start': 1583.88, 'end': 1960.39},
    {'index': 4, 'title': '04_98年美国理工博士_评论', 'kind': 'comment', 'persona': '98年美国理工博士', 'start': 1970.15, 'end': 2599.99},
    {'index': 5, 'title': '05_温温热热躺平女生_连麦', 'kind': 'call', 'persona': '温温热热躺平女生', 'start': 2601.48, 'end': 3440.69},
    {'index': 6, 'title': '06_温温热热躺平女生_评论', 'kind': 'comment', 'persona': '温温热热躺平女生', 'start': 3440.77, 'end': 3896.78},
    {'index': 7, 'title': '07_23岁top2金融博士_连麦', 'kind': 'call', 'persona': '23岁top2金融博士', 'start': 3898.45, 'end': 4643.59},
    {'index': 8, 'title': '08_23岁top2金融博士_评论', 'kind': 'comment', 'persona': '23岁top2金融博士', 'start': 4645.22, 'end': 4901.22},
    {'index': 9, 'title': '09_39岁硕士三线已婚女_连麦', 'kind': 'call', 'persona': '39岁硕士三线已婚女', 'start': 4901.22, 'end': 5850.93},
    {'index': 10, 'title': '10_39岁硕士三线已婚女_评论', 'kind': 'comment', 'persona': '39岁硕士三线已婚女', 'start': 5855.82, 'end': 6126.63},
    {'index': 11, 'title': '11_90年离异国企二孩妈_连麦', 'kind': 'call', 'persona': '90年离异国企二孩妈', 'start': 6126.63, 'end': 6547.00},
    {'index': 12, 'title': '12_90年离异国企二孩妈_评论', 'kind': 'comment', 'persona': '90年离异国企二孩妈', 'start': 6551.20, 'end': 6896.34},
    {'index': 13, 'title': '13_36岁快乐症老板恋爱_连麦', 'kind': 'call', 'persona': '36岁快乐症老板恋爱', 'start': 6896.34, 'end': 7471.38},
    {'index': 14, 'title': '14_36岁快乐症老板恋爱_评论', 'kind': 'comment', 'persona': '36岁快乐症老板恋爱', 'start': 7471.38, 'end': 8081.40},
    {'index': 15, 'title': '15_32岁自媒体医生事业_连麦', 'kind': 'call', 'persona': '32岁自媒体医生事业', 'start': 8083.44, 'end': 8826.33},
    {'index': 16, 'title': '16_32岁自媒体医生事业_评论', 'kind': 'comment', 'persona': '32岁自媒体医生事业', 'start': 8826.62, 'end': 9284.14},
    {'index': 17, 'title': '17_26岁杭州YC女孩_连麦', 'kind': 'call', 'persona': '26岁杭州YC女孩', 'start': 9284.14, 'end': 10099.78},
    {'index': 18, 'title': '18_26岁杭州YC女孩_评论', 'kind': 'comment', 'persona': '26岁杭州YC女孩', 'start': 10106.18, 'end': 10356.85},
    {'index': 19, 'title': '19_30岁医疗投资女生_连麦', 'kind': 'call', 'persona': '30岁医疗投资女生', 'start': 10356.85, 'end': 10851.26},
    {'index': 20, 'title': '20_30岁医疗投资女生_评论', 'kind': 'comment', 'persona': '30岁医疗投资女生', 'start': 10853.88, 'end': 11287.27},
    {'index': 21, 'title': '21_44岁创一代妈妈问女儿教育_连麦', 'kind': 'call', 'persona': '44岁创一代妈妈问女儿教育', 'start': 11287.27, 'end': 12194.79},
    {'index': 22, 'title': '22_44岁创一代妈妈问女儿教育_评论', 'kind': 'comment', 'persona': '44岁创一代妈妈问女儿教育', 'start': 12200.77, 'end': 12615.16},
    {'index': 23, 'title': '23_23岁普通本科与41岁男友_连麦', 'kind': 'call', 'persona': '23岁普通本科与41岁男友', 'start': 12615.16, 'end': 13042.44},
    {'index': 24, 'title': '24_23岁普通本科与41岁男友_评论', 'kind': 'comment', 'persona': '23岁普通本科与41岁男友', 'start': 13044.69, 'end': 13448.84},
    {'index': 25, 'title': '25_27岁藤校香港金融女_连麦', 'kind': 'call', 'persona': '27岁藤校香港金融女', 'start': 13448.84, 'end': 14289.89},
    {'index': 26, 'title': '26_27岁藤校香港金融女_评论', 'kind': 'comment', 'persona': '27岁藤校香港金融女', 'start': 14289.89, 'end': 14695.60},
]

# old file mapping for sections whose cleaned content can be reused directly
OLD_MAP = {
    '00_开场': '00_开场.json',
    '01_39岁医学博士短婚无娃_连麦': '01_39岁医学博士短婚无娃_连麦.json',
    '02_39岁医学博士短婚无娃_评论': '02_39岁医学博士短婚无娃_评论.json',
    '03_98年美国理工博士_连麦': '03_98年美国理工博士_连麦.json',
    '04_98年美国理工博士_评论': '04_98年美国理工博士_评论.json',
    '05_温温热热躺平女生_连麦': '05_温温热热躺平女生_连麦.json',
    '06_温温热热躺平女生_评论': '06_温温热热躺平女生_评论.json',
    '07_23岁top2金融博士_连麦': '07_23岁top2金融博士_连麦.json',
    '08_23岁top2金融博士_评论': '08_23岁top2金融博士_评论.json',
    '09_39岁硕士三线已婚女_连麦': '09_39岁硕士三线已婚女_连麦.json',
    '10_39岁硕士三线已婚女_评论': '10_39岁硕士三线已婚女_评论.json',
    '11_90年离异国企二孩妈_连麦': '11_90年离异国企二孩妈_连麦.json',
    '12_90年离异国企二孩妈_评论': '12_90年离异国企二孩妈_评论.json',
    '13_36岁快乐症老板恋爱_连麦': '13_36岁快乐症老板恋爱_连麦.json',
    '14_36岁快乐症老板恋爱_评论': '14_36岁快乐症老板恋爱_评论.json',
    '15_32岁自媒体医生事业_连麦': '15_32岁自媒体医生事业_连麦.json',
    '16_32岁自媒体医生事业_评论': '16_32岁自媒体医生事业_评论.json',
    '21_44岁创一代妈妈问女儿教育_连麦': '19_44岁创一代妈妈问女儿教育_连麦.json',
    '22_44岁创一代妈妈问女儿教育_评论': '20_44岁创一代妈妈问女儿教育_评论.json',
    '23_23岁普通本科与41岁男友_连麦': '21_23岁普通本科与41岁男友_连麦.json',
    '24_23岁普通本科与41岁男友_评论': '22_23岁普通本科与41岁男友_评论.json',
    '25_27岁藤校香港金融女_连麦': '23_27岁藤校香港金融女_连麦.json',
    '26_27岁藤校香港金融女_评论': '24_27岁藤校香港金融女_评论.json',
}

REBUILD_TITLES = {
    '17_26岁杭州YC女孩_连麦',
    '18_26岁杭州YC女孩_评论',
    '19_30岁医疗投资女生_连麦',
    '20_30岁医疗投资女生_评论',
}


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
    data = json.loads(SRC.read_text())
    segments = data['segments']
    split_summary = {
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
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        split_summary['parts'].append({
            'file': f"{part['title']}.json",
            'start': part['start'],
            'end': part['end'],
            'segments': len(part_segments),
        })
        split_summary['total_split_segments'] += len(part_segments)
    (OUT_DIR / '_split_summary.json').write_text(json.dumps(split_summary, ensure_ascii=False, indent=2) + '\n')


def normalize_sentence(sentence: dict, kind: str) -> dict:
    speaker_id = sentence.get('speaker_id', 'host')
    if kind != 'call':
        speaker_id = 'host'
    elif speaker_id not in {'host', 'guest'}:
        speaker_id = 'host'
    text = str(sentence.get('text', '')).strip()
    return {
        'speaker_id': speaker_id,
        'speaker_name': '嘉宾' if speaker_id == 'guest' else '曲曲',
        'start': float(sentence['start']),
        'end': float(sentence['end']),
        'text': text,
    }


def normalize_existing_outputs() -> None:
    for part in MANIFEST:
        title = part['title']
        if title in REBUILD_TITLES:
            continue
        old_name = OLD_MAP[title]
        old_path = OUT_DIR / old_name
        obj = json.loads(old_path.read_text())
        sentences = [normalize_sentence(s, part['kind']) for s in obj['sentences'] if str(s.get('text', '')).strip()]
        notes = obj.get('meta', {}).get('notes') or '沿用既有人工整理结果，并统一规范为 formal_output.schema.json。'
        normalized = {
            'meta': {
                'source_file': SOURCE_FILE_NAME,
                'index': part['index'],
                'kind': part['kind'],
                'persona': part['persona'],
                'title': title,
                'start': part['start'],
                'end': part['end'],
                'start_ts': ts(part['start']),
                'end_ts': ts(part['end']),
                'raw_segment_count': next(x['segments'] for x in json.loads((OUT_DIR / '_split_summary.json').read_text())['parts'] if x['file'] == f'{title}.json'),
                'speaker_ids': speaker_ids(part['kind']),
                'speaker_names': speaker_names(part['kind']),
                'sentence_count': len(sentences),
                'notes': notes,
            },
            'sentences': sentences,
        }
        new_path = OUT_DIR / f'{title}.json'
        new_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + '\n')
        if new_path.name != old_name and old_path.exists():
            old_path.unlink()


def write_prompt_files() -> None:
    template = '''请处理文件 `{raw_path}`，并把最终答案直接输出为**纯 JSON 对象**（不要 markdown，不要代码块，不要额外说明）。

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
12. 输出必须严格符合 schema：`data/03_transcripts/formal_output.schema.json`。

输出结构：
{{
  "meta": {{...}},
  "sentences": [
    {{"speaker_id":"host|guest","speaker_name":"曲曲|嘉宾","start":0,"end":0,"text":"..."}}
  ]
}}
'''
    for part in MANIFEST:
        if part['title'] not in REBUILD_TITLES:
            continue
        kind = part['kind']
        prompt = template.format(
            raw_path=str(RAW_DIR / f"{part['title']}.json"),
            kind=kind,
            speaker_rule=('只允许两个说话人：`host` = 曲曲，`guest` = 嘉宾。' if kind == 'call' else '这是单人段，只允许 `host` = 曲曲。'),
            speaker_ids='["host", "guest"]' if kind == 'call' else '["host"]',
            speaker_names='{"host":"曲曲","guest":"嘉宾"}' if kind == 'call' else '{"host":"曲曲"}',
            source_file=SOURCE_FILE_NAME,
            title=part['title'],
        )
        (PROMPT_DIR / f"{part['title']}.md").write_text(prompt)


def validate_dir() -> None:
    expected_titles = {f"{part['title']}.json" for part in MANIFEST}
    found_titles = {p.name for p in OUT_DIR.glob('*.json') if not p.name.startswith('_')}
    assert expected_titles == found_titles, (sorted(expected_titles - found_titles), sorted(found_titles - expected_titles))
    for part in MANIFEST:
        path = OUT_DIR / f"{part['title']}.json"
        obj = json.loads(path.read_text())
        assert set(obj.keys()) == {'meta', 'sentences'}, path
        meta = obj['meta']
        sentences = obj['sentences']
        expected_meta = {'source_file','index','kind','persona','title','start','end','start_ts','end_ts','raw_segment_count','speaker_ids','speaker_names','sentence_count','notes'}
        assert set(meta.keys()) == expected_meta, (path, sorted(meta.keys()))
        assert meta['index'] == part['index'], path
        assert meta['kind'] == part['kind'], path
        assert meta['persona'] == part['persona'], path
        assert meta['title'] == part['title'], path
        assert meta['source_file'] == SOURCE_FILE_NAME, path
        assert meta['speaker_ids'] == speaker_ids(part['kind']), path
        assert meta['speaker_names'] == speaker_names(part['kind']), path
        assert meta['sentence_count'] == len(sentences), path
        allowed = set(speaker_ids(part['kind']))
        for s in sentences:
            assert set(s.keys()) == {'speaker_id','speaker_name','start','end','text'}, (path, s.keys())
            assert s['speaker_id'] in allowed, (path, s)
            assert s['speaker_name'] == ('嘉宾' if s['speaker_id'] == 'guest' else '曲曲'), (path, s)
            assert isinstance(s['text'], str), (path, s)


def main() -> None:
    build_raw_sections()
    normalize_existing_outputs()
    write_prompt_files()
    print('prepared_raw_sections', len(MANIFEST))
    print('prepared_existing_normalized', len(MANIFEST) - len(REBUILD_TITLES))
    print('need_codex_exec', len(REBUILD_TITLES))


if __name__ == '__main__':
    main()
