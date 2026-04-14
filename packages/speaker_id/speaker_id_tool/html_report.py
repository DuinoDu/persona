from __future__ import annotations

import json
from html import escape
from pathlib import Path


def render_part_comparison_html(payload: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_part_comparison_html(payload), encoding="utf-8")
    return output_path


def build_part_comparison_html(payload: dict) -> str:
    part_path = payload["part_path"]
    meta = payload.get("meta", {})
    speaker_names = meta.get("speaker_names", {})
    original_sentences = payload["original"]["sentences"]
    before_predictions = {item["sentence_index"]: item for item in payload["before"]["predictions"]}
    after_predictions = {item["sentence_index"]: item for item in payload["after"]["predictions"]}
    changed_indices = {item["sentence_index"] for item in payload.get("changed_sentences", [])}
    corrected_summary = payload.get("after", {}).get("corrected_summary", {})
    split_sentence_count = corrected_summary.get("split_sentence_count", 0)

    before_agreement = format_percent(payload["before"]["summary"].get("agreement"))
    after_agreement = format_percent(payload["after"]["summary"].get("agreement"))
    improvement = compute_improvement(
        payload["before"]["summary"].get("agreement"),
        payload["after"]["summary"].get("agreement"),
    )
    payload_json = safe_json_for_script(payload)

    rows = []
    for sentence in original_sentences:
        idx = sentence["sentence_index"]
        before_item = before_predictions[idx]
        after_item = after_predictions[idx]
        changed = idx in changed_indices
        rows.append(
            f"""
            <section class="row {'changed' if changed else ''}">
              <div class="row-head">
                <div class="row-title">#{idx} · {escape(format_range(sentence['start'], sentence['end']))}</div>
                <div class="row-tags">
                  {'<span class="badge badge-change">算法修正</span>' if changed else '<span class="badge badge-quiet">未改动</span>'}
                  {'<span class="badge badge-split">句内切分</span>' if after_item.get('split_applied') else ''}
                  {'<span class="badge badge-warn">overlap</span>' if after_item.get('overlap_suspected') else ''}
                  <span class="badge badge-conf">置信度 {after_item.get('confidence', 0):.2f}</span>
                </div>
              </div>
              <div class="columns">
                {render_column_panel('原始', sentence['speaker_id'], sentence['text'], speaker_names, extra=f"原始 speaker_id: {sentence['speaker_id'] or 'unknown'}")}
                {render_corrected_panel(after_item, speaker_names, before_item)}
              </div>
            </section>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(Path(part_path).name)} · ququ-speaker-id</title>
  <style>
    :root {{
      --bg: #0b1020;
      --panel: #111827;
      --panel-2: #0f172a;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --border: #223047;
      --host: #2563eb;
      --guest: #db2777;
      --warn: #f59e0b;
      --ok: #22c55e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #0b1020 0%, #0a1226 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
      line-height: 1.5;
    }}
    .wrap {{
      width: min(1480px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 48px;
    }}
    .hero {{
      background: rgba(17, 24, 39, 0.92);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.24);
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 28px;
      line-height: 1.2;
    }}
    .sub {{
      color: var(--muted);
      font-size: 14px;
      word-break: break-all;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .card {{
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px 16px;
    }}
    .card .label {{
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .card .value {{
      font-size: 26px;
      font-weight: 700;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
      color: var(--muted);
      font-size: 13px;
    }}
    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }}
    .dot.host {{ background: var(--host); }}
    .dot.guest {{ background: var(--guest); }}
    .rows {{
      display: grid;
      gap: 14px;
    }}
    .data-panel {{
      margin-top: 18px;
      background: rgba(15, 23, 42, 0.94);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
      margin-bottom: 12px;
    }}
    .btn {{
      appearance: none;
      border: 1px solid rgba(148, 163, 184, 0.28);
      background: rgba(30, 41, 59, 0.88);
      color: var(--text);
      border-radius: 10px;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 13px;
    }}
    .btn:hover {{
      border-color: rgba(96, 165, 250, 0.55);
    }}
    .json-wrap {{
      display: none;
      margin-top: 12px;
    }}
    .json-wrap.open {{
      display: block;
    }}
    pre.json-view {{
      margin: 0;
      max-height: 420px;
      overflow: auto;
      border-radius: 12px;
      padding: 14px;
      background: rgba(2, 6, 23, 0.92);
      border: 1px solid var(--border);
      color: #cbd5e1;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .row {{
      background: rgba(15, 23, 42, 0.94);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px;
    }}
    .row.changed {{
      border-color: rgba(245, 158, 11, 0.7);
      box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.18);
    }}
    .row-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }}
    .row-title {{
      font-size: 13px;
      color: var(--muted);
    }}
    .row-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .badge {{
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid rgba(148, 163, 184, 0.22);
      color: #dbeafe;
      background: rgba(30, 41, 59, 0.8);
    }}
    .badge-change {{ border-color: rgba(245, 158, 11, 0.45); color: #fde68a; }}
    .badge-split {{ border-color: rgba(96, 165, 250, 0.45); color: #bfdbfe; }}
    .badge-warn {{ border-color: rgba(245, 158, 11, 0.45); color: #fdba74; }}
    .badge-conf {{ border-color: rgba(34, 197, 94, 0.35); color: #bbf7d0; }}
    .badge-quiet {{ color: var(--muted); }}
    .columns {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .panel {{
      border: 1px solid var(--border);
      border-radius: 14px;
      background: rgba(17, 24, 39, 0.92);
      padding: 12px;
      min-height: 118px;
    }}
    .panel-title {{
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 10px;
    }}
    .bubble-wrap {{
      display: flex;
      margin-bottom: 10px;
    }}
    .bubble-wrap.host {{ justify-content: flex-start; }}
    .bubble-wrap.guest {{ justify-content: flex-end; }}
    .bubble-wrap.unknown {{ justify-content: center; }}
    .bubble {{
      max-width: 86%;
      padding: 12px 14px;
      border-radius: 16px;
      white-space: pre-wrap;
      word-break: break-word;
      box-shadow: inset 0 -1px 0 rgba(255, 255, 255, 0.08);
    }}
    .bubble.host {{ background: rgba(37, 99, 235, 0.92); }}
    .bubble.guest {{ background: rgba(219, 39, 119, 0.9); }}
    .bubble.unknown {{ background: rgba(71, 85, 105, 0.9); }}
    .bubble-range {{
      font-size: 11px;
      opacity: 0.82;
      margin-bottom: 6px;
    }}
    .panel-meta {{
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 960px) {{
      .columns {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <header class="hero">
      <h1>{escape(meta.get('title') or Path(part_path).stem)}</h1>
      <div class="sub">{escape(part_path)}</div>
      <div class="stats">
        <div class="card">
          <div class="label">处理前识别率</div>
          <div class="value">{before_agreement}</div>
        </div>
        <div class="card">
          <div class="label">处理后识别率</div>
          <div class="value">{after_agreement}</div>
        </div>
        <div class="card">
          <div class="label">提升</div>
          <div class="value">{improvement}</div>
        </div>
        <div class="card">
          <div class="label">被算法修正句数</div>
          <div class="value">{len(changed_indices)}</div>
        </div>
        <div class="card">
          <div class="label">句内切分句数</div>
          <div class="value">{split_sentence_count}</div>
        </div>
      </div>
      <div class="legend">
        <span><i class="dot host"></i>Host：{escape(speaker_names.get('host', 'host'))}</span>
        <span><i class="dot guest"></i>Guest：{escape(speaker_names.get('guest', 'guest'))}</span>
        <span>Backend：{escape(payload['feature_backend'])}</span>
        <span>HTML 已内嵌完整 part/comparison JSON</span>
      </div>
    </header>
    <section class="rows">
      {''.join(rows)}
    </section>
    <section class="data-panel">
      <div class="row-head">
        <div class="row-title">完整 part 数据 / comparison payload</div>
        <div class="row-tags">
          <span class="badge badge-conf">内嵌 JSON</span>
        </div>
      </div>
      <div class="actions">
        <button class="btn" type="button" id="toggle-json">显示 JSON</button>
        <button class="btn" type="button" id="copy-json">复制 JSON</button>
        <button class="btn" type="button" id="download-json">下载 JSON</button>
      </div>
      <div class="json-wrap" id="json-wrap">
        <pre class="json-view" id="json-view"></pre>
      </div>
    </section>
  </main>
  <script id="part-comparison-data" type="application/json">{payload_json}</script>
  <script>
    (() => {{
      const payloadEl = document.getElementById('part-comparison-data');
      const jsonWrap = document.getElementById('json-wrap');
      const jsonView = document.getElementById('json-view');
      const toggleBtn = document.getElementById('toggle-json');
      const copyBtn = document.getElementById('copy-json');
      const downloadBtn = document.getElementById('download-json');
      const raw = payloadEl.textContent || '{{}}';
      const pretty = JSON.stringify(JSON.parse(raw), null, 2);
      jsonView.textContent = pretty;

      toggleBtn.addEventListener('click', () => {{
        const open = jsonWrap.classList.toggle('open');
        toggleBtn.textContent = open ? '隐藏 JSON' : '显示 JSON';
      }});

      copyBtn.addEventListener('click', async () => {{
        await navigator.clipboard.writeText(pretty);
        copyBtn.textContent = '已复制';
        setTimeout(() => copyBtn.textContent = '复制 JSON', 1200);
      }});

      downloadBtn.addEventListener('click', () => {{
        const blob = new Blob([pretty], {{ type: 'application/json;charset=utf-8' }});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'part-comparison.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }});

      window.__PART_COMPARISON__ = JSON.parse(raw);
    }})();
  </script>
</body>
</html>
"""


def render_column_panel(title: str, speaker_id: str | None, text: str, speaker_names: dict, extra: str) -> str:
    speaker = normalize_speaker(speaker_id)
    speaker_label = speaker_names.get(speaker, speaker or "unknown")
    return f"""
    <article class="panel">
      <div class="panel-title">{escape(title)}</div>
      <div class="bubble-wrap {escape(speaker)}">
        <div class="bubble {escape(speaker)}">{escape(text)}</div>
      </div>
      <div class="panel-meta">角色：{escape(speaker_label)} · {escape(extra)}</div>
    </article>
    """


def render_corrected_panel(after_item: dict, speaker_names: dict, before_item: dict) -> str:
    corrected_segments = after_item.get("corrected_segments") or [
        {
            "start": after_item.get("start"),
            "end": after_item.get("end"),
            "text": after_item.get("text", ""),
            "predicted_speaker_id": after_item.get("predicted_speaker_id"),
        }
    ]
    bubbles = []
    for segment in corrected_segments:
        speaker = normalize_speaker(segment.get("predicted_speaker_id"))
        speaker_label = speaker_names.get(speaker, speaker or "unknown")
        bubbles.append(
            f"""
            <div class="bubble-wrap {escape(speaker)}">
              <div class="bubble {escape(speaker)}">
                <div class="bubble-range">{escape(format_range(segment.get('start', 0.0), segment.get('end', 0.0)))} · {escape(speaker_label)}</div>
                {escape(segment.get('text') or '')}
              </div>
            </div>
            """
        )
    return f"""
    <article class="panel">
      <div class="panel-title">修正后</div>
      {''.join(bubbles)}
      <div class="panel-meta">{escape(render_after_extra(before_item, after_item))}</div>
    </article>
    """


def render_after_extra(before_item: dict, after_item: dict) -> str:
    before_role = before_item.get("predicted_speaker_id") or "unknown"
    after_role = after_item.get("predicted_speaker_id") or "unknown"
    corrected_segments = after_item.get("corrected_segments") or []
    if len(corrected_segments) > 1:
        timeline = " / ".join(segment.get("predicted_speaker_id") or "unknown" for segment in corrected_segments)
        return f"baseline: {before_role} → corrected timeline: {timeline}"
    return f"baseline: {before_role} → corrected: {after_role}"


def normalize_speaker(value: str | None) -> str:
    if value in {"host", "guest"}:
        return value
    return "unknown"


def format_range(start: float, end: float) -> str:
    return f"{format_time(start)} - {format_time(end)}"


def format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remainder = seconds - hours * 3600 - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{remainder:05.2f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def compute_improvement(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return "N/A"
    delta = (after - before) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.2f} pp"


def safe_json_for_script(payload: dict) -> str:
    return (
        json.dumps(payload, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
    )
