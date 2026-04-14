from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .backends import BackendConfig, create_backend
from .cache import EmbeddingCache, clear_embedding_cache, summarize_embedding_cache
from .config import (
    DEFAULT_DOWNLOADS_ROOT,
    DEFAULT_EMBEDDING_CACHE_DIR,
    DEFAULT_HOST_BANK_PATH,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PARTS_ROOT,
    DEFAULT_TRANSCRIPTS_ROOT,
)
from .data import DataIndex
from .html_report import render_part_comparison_html
from .pipeline import (
    analyze_dataset,
    analyze_part,
    build_host_bank,
    compare_part_predictions,
    ensure_output_dir,
    load_host_bank,
    warm_cache_for_dataset,
    warm_cache_for_part,
)

app = typer.Typer(no_args_is_help=True)
console = Console()


def make_index(downloads_root: Path, transcripts_root: Path) -> DataIndex:
    return DataIndex(downloads_root=downloads_root, transcripts_root=transcripts_root)


def make_backend(
    backend: str,
    device: str,
    wespeaker_model: str,
    wespeaker_cache_dir: Path,
):
    return create_backend(
        BackendConfig(
            backend=backend,
            device=device,
            wespeaker_model=wespeaker_model,
            wespeaker_cache_dir=wespeaker_cache_dir,
        )
    )


def make_embedding_cache(embedding_cache_dir: Path, backend_impl) -> EmbeddingCache:
    return EmbeddingCache(
        root=embedding_cache_dir,
        backend_name=backend_impl.name,
        backend_identity=backend_impl.cache_identity(),
    )


def cache_summary_table(title: str, snapshot: dict) -> Table:
    table = Table(title=title)
    table.add_column("Metric")
    table.add_column("Value")
    for key in ["path", "backend", "exists", "entry_count", "total_bytes", "hits", "misses", "writes", "lookups", "hit_rate"]:
        if key in snapshot:
            table.add_row(key, str(snapshot[key]))
    return table


def percent_string(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def load_part_paths_from_list_file(list_file: Path) -> list[Path]:
    payload = json.loads(list_file.read_text())
    if isinstance(payload, list):
        return [Path(item) for item in payload]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        paths = []
        for item in payload["items"]:
            if isinstance(item, dict) and "path" in item:
                paths.append(Path(item["path"]))
        return paths
    raise typer.BadParameter(f"Unsupported list file format: {list_file}")


def build_fixed_sentences(part_payload: dict, comparison: dict) -> list[dict]:
    speaker_names = part_payload.get("meta", {}).get("speaker_names", {})
    corrected = comparison["after"].get("corrected_sentences", [])
    fixed_sentences = []
    for item in corrected:
        speaker_id = item.get("predicted_speaker_id")
        fixed_sentences.append(
            {
                "speaker_id": speaker_id,
                "speaker_name": speaker_names.get(speaker_id, speaker_id),
                "start": item["start"],
                "end": item["end"],
                "text": item.get("text", ""),
            }
        )
    return fixed_sentences


def append_note(notes: object, note: str) -> str:
    if not notes:
        return note
    if isinstance(notes, str):
        if note in notes:
            return notes
        return f"{notes} | {note}"
    return note


def build_fixed_part_payload(part_file: Path, comparison: dict) -> dict:
    original_payload = json.loads(part_file.read_text())
    fixed_sentences = build_fixed_sentences(original_payload, comparison)
    meta = dict(original_payload.get("meta", {}))
    present_speaker_ids = [
        speaker_id
        for speaker_id in ["host", "guest"]
        if any(item["speaker_id"] == speaker_id for item in fixed_sentences)
    ]
    meta["speaker_ids"] = present_speaker_ids
    meta["sentence_count"] = len(fixed_sentences)
    meta["notes"] = append_note(meta.get("notes"), "speaker_id_tool_fixed_export_v1")
    meta["fixed_from_part_path"] = str(part_file)
    meta["fixed_backend"] = comparison["feature_backend"]
    meta["fixed_changed_sentence_count"] = len(comparison.get("changed_sentences", []))
    meta["fixed_split_sentence_count"] = comparison["after"].get("corrected_summary", {}).get(
        "split_sentence_count", 0
    )
    return {
        "meta": meta,
        "sentences": fixed_sentences,
    }


def resolve_fixed_output_path(part_file: Path, output_dir: Path, parts_root: Path) -> Path:
    try:
        relative = part_file.relative_to(parts_root)
    except ValueError:
        relative = Path(part_file.name)
    return output_dir / relative


@app.command("build-host-bank")
def build_host_bank_command(
    downloads_root: Path = typer.Option(DEFAULT_DOWNLOADS_ROOT),
    transcripts_root: Path = typer.Option(DEFAULT_TRANSCRIPTS_ROOT),
    parts_root: Path = typer.Option(DEFAULT_PARTS_ROOT),
    output_path: Path = typer.Option(DEFAULT_HOST_BANK_PATH),
    backend: str = typer.Option("spectrum"),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
    max_parts: int = typer.Option(300, min=1),
    max_segments: int = typer.Option(1200, min=10),
) -> None:
    ensure_output_dir(output_path.parent)
    backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
    embedding_cache = make_embedding_cache(embedding_cache_dir, backend_impl)
    payload = build_host_bank(
        parts_root=parts_root,
        data_index=make_index(downloads_root, transcripts_root),
        backend=backend_impl,
        output_path=output_path,
        max_parts=max_parts,
        max_segments=max_segments,
        embedding_cache=embedding_cache,
    )
    console.print(f"[green]host bank written[/green] {output_path}")
    table = Table(title="Host Bank")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("backend", str(payload["feature_backend"]))
    table.add_row("feature_backend", str(payload["feature_backend"]))
    table.add_row("part_count", str(payload["part_count"]))
    table.add_row("segment_count", str(payload["segment_count"]))
    table.add_row("vector_dim", str(len(payload["centroid"])))
    table.add_row("cache_hits", str(payload["embedding_cache"]["hits"]))
    table.add_row("cache_misses", str(payload["embedding_cache"]["misses"]))
    table.add_row("cache_writes", str(payload["embedding_cache"]["writes"]))
    console.print(table)


@app.command("analyze-part")
def analyze_part_command(
    part_file: Path = typer.Option(..., exists=True, readable=True),
    downloads_root: Path = typer.Option(DEFAULT_DOWNLOADS_ROOT),
    transcripts_root: Path = typer.Option(DEFAULT_TRANSCRIPTS_ROOT),
    host_bank_path: Path = typer.Option(DEFAULT_HOST_BANK_PATH),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_ROOT / "parts"),
    backend: str = typer.Option("spectrum"),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
) -> None:
    ensure_output_dir(output_dir)
    host_bank = load_host_bank(host_bank_path)
    backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
    embedding_cache = make_embedding_cache(embedding_cache_dir, backend_impl)
    report = analyze_part(
        part_path=part_file,
        data_index=make_index(downloads_root, transcripts_root),
        backend=backend_impl,
        host_bank=host_bank,
        output_dir=output_dir,
        embedding_cache=embedding_cache,
    )
    table = Table(title="Part Analysis")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("part", report["part_path"])
    table.add_row("backend", report["feature_backend"])
    table.add_row("mode", str(report["cluster_summary"].get("mode")))
    table.add_row("usable_segment_count", str(report["cluster_summary"].get("usable_segment_count")))
    table.add_row(
        "overlap_count",
        str(sum(1 for item in report["predictions"] if item["overlap_suspected"])),
    )
    table.add_row(
        "low_confidence_count",
        str(sum(1 for item in report["predictions"] if item["confidence"] < 0.6)),
    )
    table.add_row("cache_hits", str(report["embedding_cache"]["hits"]))
    table.add_row("cache_misses", str(report["embedding_cache"]["misses"]))
    table.add_row("cache_writes", str(report["embedding_cache"]["writes"]))
    console.print(table)


@app.command("render-html")
def render_html_command(
    part_file: Path = typer.Option(..., exists=True, readable=True),
    downloads_root: Path = typer.Option(DEFAULT_DOWNLOADS_ROOT),
    transcripts_root: Path = typer.Option(DEFAULT_TRANSCRIPTS_ROOT),
    host_bank_path: Path = typer.Option(DEFAULT_HOST_BANK_PATH),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_ROOT / "html"),
    output_path: Path | None = typer.Option(None),
    comparison_json_path: Path | None = typer.Option(None),
    backend: str = typer.Option("spectrum"),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
) -> None:
    ensure_output_dir(output_dir)
    host_bank = load_host_bank(host_bank_path)
    backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
    embedding_cache = make_embedding_cache(embedding_cache_dir, backend_impl)
    comparison = compare_part_predictions(
        part_path=part_file,
        data_index=make_index(downloads_root, transcripts_root),
        backend=backend_impl,
        host_bank=host_bank,
        embedding_cache=embedding_cache,
    )
    if output_path is None:
        output_path = output_dir / f"{part_file.stem}.html"
    render_part_comparison_html(comparison, output_path)
    if comparison_json_path is not None:
        ensure_output_dir(comparison_json_path.parent)
        comparison_json_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2))

    before_summary = comparison["before"]["summary"]
    after_summary = comparison["after"]["summary"]
    improvement = None
    if before_summary["agreement"] is not None and after_summary["agreement"] is not None:
        improvement = (after_summary["agreement"] - before_summary["agreement"]) * 100

    table = Table(title="HTML Comparison")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("part", comparison["part_path"])
    table.add_row("backend", comparison["feature_backend"])
    table.add_row("before_agreement", percent_string(before_summary["agreement"]))
    table.add_row("after_agreement", percent_string(after_summary["agreement"]))
    table.add_row("improvement_pp", "N/A" if improvement is None else f"{improvement:+.2f}")
    table.add_row("changed_sentence_count", str(len(comparison["changed_sentences"])))
    table.add_row("html_path", str(output_path))
    if comparison_json_path is not None:
        table.add_row("comparison_json_path", str(comparison_json_path))
    table.add_row("cache_hits", str(comparison["embedding_cache"]["hits"]))
    table.add_row("cache_misses", str(comparison["embedding_cache"]["misses"]))
    console.print(table)


@app.command("analyze-dataset")
def analyze_dataset_command(
    downloads_root: Path = typer.Option(DEFAULT_DOWNLOADS_ROOT),
    transcripts_root: Path = typer.Option(DEFAULT_TRANSCRIPTS_ROOT),
    parts_root: Path = typer.Option(DEFAULT_PARTS_ROOT),
    host_bank_path: Path = typer.Option(DEFAULT_HOST_BANK_PATH),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_ROOT / "dataset"),
    backend: str = typer.Option("spectrum"),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
    limit: int | None = typer.Option(None, min=1),
) -> None:
    ensure_output_dir(output_dir)
    host_bank = load_host_bank(host_bank_path)
    backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
    embedding_cache = make_embedding_cache(embedding_cache_dir, backend_impl)
    started_at = time.perf_counter()
    reports = analyze_dataset(
        parts_root=parts_root,
        data_index=make_index(downloads_root, transcripts_root),
        backend=backend_impl,
        host_bank=host_bank,
        output_dir=output_dir,
        limit=limit,
        embedding_cache=embedding_cache,
    )
    elapsed_sec = time.perf_counter() - started_at
    success = sum(1 for report in reports if "error" not in report)
    console.print(f"[green]dataset analyzed[/green] success={success} total={len(reports)}")
    metrics = {
        "backend": backend_impl.name,
        "elapsed_sec": elapsed_sec,
        "success": success,
        "total": len(reports),
        "cache": embedding_cache.snapshot(),
    }
    (output_dir / "dataset_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    console.print(
        f"embedding_cache hits={embedding_cache.hit_count} misses={embedding_cache.miss_count} writes={embedding_cache.write_count} hit_rate={metrics['cache']['hit_rate']}"
    )
    console.print(f"elapsed_sec={elapsed_sec:.3f}")


@app.command("clear-cache")
def clear_cache_command(
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
    backend: str | None = typer.Option(None),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
) -> None:
    backend_name = None
    if backend is not None:
        backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
        backend_name = backend_impl.name
    before = summarize_embedding_cache(embedding_cache_dir, backend_name)
    result = clear_embedding_cache(embedding_cache_dir, backend_name)
    console.print(cache_summary_table("Embedding Cache Cleared", result))
    if not before["exists"]:
        console.print("[yellow]cache path did not exist[/yellow]")


@app.command("warm-cache")
def warm_cache_command(
    downloads_root: Path = typer.Option(DEFAULT_DOWNLOADS_ROOT),
    transcripts_root: Path = typer.Option(DEFAULT_TRANSCRIPTS_ROOT),
    parts_root: Path = typer.Option(DEFAULT_PARTS_ROOT),
    output_path: Path = typer.Option(DEFAULT_OUTPUT_ROOT / "cache_warm_summary.json"),
    part_file: Path | None = typer.Option(None),
    backend: str = typer.Option("spectrum"),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
    limit: int | None = typer.Option(None, min=1),
) -> None:
    ensure_output_dir(output_path.parent)
    if part_file is not None and not part_file.exists():
        raise typer.BadParameter(f"part_file not found: {part_file}")
    backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
    embedding_cache = make_embedding_cache(embedding_cache_dir, backend_impl)
    data_index = make_index(downloads_root, transcripts_root)
    started_at = time.perf_counter()
    if part_file is not None:
        reports = [
            warm_cache_for_part(
                part_path=part_file,
                data_index=data_index,
                backend=backend_impl,
                embedding_cache=embedding_cache,
            )
        ]
    else:
        reports = warm_cache_for_dataset(
            parts_root=parts_root,
            data_index=data_index,
            backend=backend_impl,
            embedding_cache=embedding_cache,
            limit=limit,
        )
    elapsed_sec = time.perf_counter() - started_at
    success = sum(1 for report in reports if "error" not in report)
    payload = {
        "backend": backend_impl.name,
        "elapsed_sec": elapsed_sec,
        "success": success,
        "total": len(reports),
        "cache": embedding_cache.snapshot(),
        "reports": reports,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    console.print(f"[green]cache warmed[/green] success={success} total={len(reports)} output={output_path}")
    console.print(
        f"embedding_cache hits={embedding_cache.hit_count} misses={embedding_cache.miss_count} writes={embedding_cache.write_count} hit_rate={payload['cache']['hit_rate']}"
    )
    console.print(f"elapsed_sec={elapsed_sec:.3f}")


@app.command("export-fixed-part")
def export_fixed_part_command(
    part_file: Path = typer.Option(..., exists=True, readable=True),
    downloads_root: Path = typer.Option(DEFAULT_DOWNLOADS_ROOT),
    transcripts_root: Path = typer.Option(DEFAULT_TRANSCRIPTS_ROOT),
    parts_root: Path = typer.Option(DEFAULT_PARTS_ROOT),
    host_bank_path: Path = typer.Option(DEFAULT_HOST_BANK_PATH),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_ROOT / "fixed_parts"),
    backend: str = typer.Option("spectrum"),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
) -> None:
    ensure_output_dir(output_dir)
    host_bank = load_host_bank(host_bank_path)
    backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
    embedding_cache = make_embedding_cache(embedding_cache_dir, backend_impl)
    comparison = compare_part_predictions(
        part_path=part_file,
        data_index=make_index(downloads_root, transcripts_root),
        backend=backend_impl,
        host_bank=host_bank,
        embedding_cache=embedding_cache,
    )
    fixed_payload = build_fixed_part_payload(part_file, comparison)
    output_path = resolve_fixed_output_path(part_file, output_dir, parts_root)
    ensure_output_dir(output_path.parent)
    output_path.write_text(json.dumps(fixed_payload, ensure_ascii=False, indent=2))

    fixed_sentence_count = len(fixed_payload["sentences"])
    host_count = sum(1 for item in fixed_payload["sentences"] if item["speaker_id"] == "host")
    guest_count = sum(1 for item in fixed_payload["sentences"] if item["speaker_id"] == "guest")
    table = Table(title="Fixed Part Export")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("part", str(part_file))
    table.add_row("output_path", str(output_path))
    table.add_row("backend", comparison["feature_backend"])
    table.add_row("fixed_sentence_count", str(fixed_sentence_count))
    table.add_row("host_count", str(host_count))
    table.add_row("guest_count", str(guest_count))
    console.print(table)


@app.command("export-fixed-list")
def export_fixed_list_command(
    list_file: Path = typer.Option(..., exists=True, readable=True),
    downloads_root: Path = typer.Option(DEFAULT_DOWNLOADS_ROOT),
    transcripts_root: Path = typer.Option(DEFAULT_TRANSCRIPTS_ROOT),
    parts_root: Path = typer.Option(DEFAULT_PARTS_ROOT),
    host_bank_path: Path = typer.Option(DEFAULT_HOST_BANK_PATH),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_ROOT / "fixed_parts"),
    backend: str = typer.Option("spectrum"),
    device: str = typer.Option("cpu"),
    wespeaker_model: str = typer.Option("chinese"),
    wespeaker_cache_dir: Path = typer.Option(Path(".cache/wespeaker")),
    embedding_cache_dir: Path = typer.Option(DEFAULT_EMBEDDING_CACHE_DIR),
) -> None:
    ensure_output_dir(output_dir)
    part_files = load_part_paths_from_list_file(list_file)
    host_bank = load_host_bank(host_bank_path)
    backend_impl = make_backend(backend, device, wespeaker_model, wespeaker_cache_dir)
    embedding_cache = make_embedding_cache(embedding_cache_dir, backend_impl)
    data_index = make_index(downloads_root, transcripts_root)

    exported = []
    errors = []
    started_at = time.perf_counter()
    for idx, part_file in enumerate(part_files, start=1):
        try:
            comparison = compare_part_predictions(
                part_path=part_file,
                data_index=data_index,
                backend=backend_impl,
                host_bank=host_bank,
                embedding_cache=embedding_cache,
            )
            fixed_payload = build_fixed_part_payload(part_file, comparison)
            output_path = resolve_fixed_output_path(part_file, output_dir, parts_root)
            ensure_output_dir(output_path.parent)
            output_path.write_text(json.dumps(fixed_payload, ensure_ascii=False, indent=2))
            exported.append(
                {
                    "part_path": str(part_file),
                    "output_path": str(output_path),
                    "fixed_sentence_count": len(fixed_payload["sentences"]),
                    "host_count": sum(
                        1 for item in fixed_payload["sentences"] if item["speaker_id"] == "host"
                    ),
                    "guest_count": sum(
                        1 for item in fixed_payload["sentences"] if item["speaker_id"] == "guest"
                    ),
                }
            )
        except Exception as exc:
            errors.append({"part_path": str(part_file), "error": str(exc)})
        if idx % 10 == 0 or idx == len(part_files):
            console.print(f"export progress {idx}/{len(part_files)}")

    elapsed_sec = time.perf_counter() - started_at
    payload = {
        "list_file": str(list_file),
        "backend": backend_impl.name,
        "elapsed_sec": elapsed_sec,
        "exported_count": len(exported),
        "error_count": len(errors),
        "output_dir": str(output_dir),
        "exports": exported,
        "errors": errors,
    }
    manifest_path = output_dir / "_export_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    table = Table(title="Fixed List Export")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("list_file", str(list_file))
    table.add_row("backend", backend_impl.name)
    table.add_row("exported_count", str(len(exported)))
    table.add_row("error_count", str(len(errors)))
    table.add_row("output_dir", str(output_dir))
    table.add_row("manifest_path", str(manifest_path))
    console.print(table)


if __name__ == "__main__":
    app()
