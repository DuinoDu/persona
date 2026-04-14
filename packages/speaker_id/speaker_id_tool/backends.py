from __future__ import annotations

import os
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
import requests
import torch
import torch.nn.functional as F
import torchaudio
import torchaudio.compliance.kaldi as kaldi
import yaml
from rich.console import Console

from .config import SAMPLE_RATE
from .features import spectrum_embedding
from .vendor_wespeaker.models.speaker_model import get_speaker_model
from .vendor_wespeaker.utils.checkpoint import load_checkpoint

console = Console()


@dataclass(slots=True)
class BackendConfig:
    backend: str
    device: str = "cpu"
    wespeaker_model: str = "chinese"
    wespeaker_cache_dir: Path = Path(".cache/wespeaker")


class EmbeddingBackend:
    name: str

    def extract(self, waveform: np.ndarray, sample_rate: int) -> np.ndarray:
        raise NotImplementedError

    def export_config(self) -> dict:
        raise NotImplementedError

    def cache_identity(self) -> dict:
        return self.export_config()


class SpectrumBackend(EmbeddingBackend):
    name = "spectrum-mfcc"

    def extract(self, waveform: np.ndarray, sample_rate: int) -> np.ndarray:
        return spectrum_embedding(waveform, sr=sample_rate)

    def export_config(self) -> dict:
        return {"backend": "spectrum"}

    def cache_identity(self) -> dict:
        return {"backend": "spectrum"}


class WeSpeakerBackend(EmbeddingBackend):
    name = "wespeaker"
    assets = {
        "chinese": "cnceleb_resnet34.tar.gz",
        "english": "voxceleb_resnet221_LM.tar.gz",
        "campplus": "campplus_cn_common_200k.tar.gz",
        "eres2net": "eres2net_cn_commom_200k.tar.gz",
        "vblinkp": "voxblink2_samresnet34.zip",
        "vblinkf": "voxblink2_samresnet34_ft.zip",
        "w2vbert2_mfa": "voxceleb_voxblink2_w2v_bert2_lora_adapterMFA_lm.tar.gz",
    }

    def __init__(self, model_name: str, cache_dir: Path, device: str = "cpu"):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.device = torch.device(device)
        model_dir = self._resolve_model_dir()
        self.model = self._load_model(model_dir)
        self.model = self.model.to(self.device)
        self.model.eval()

    def export_config(self) -> dict:
        return {
            "backend": "wespeaker",
            "wespeaker_model": self.model_name,
            "device": str(self.device),
            "wespeaker_cache_dir": str(self.cache_dir),
        }

    def cache_identity(self) -> dict:
        return {
            "backend": "wespeaker",
            "wespeaker_model": self.model_name,
        }

    def extract(self, waveform: np.ndarray, sample_rate: int) -> np.ndarray:
        if waveform.size == 0:
            return np.zeros(256, dtype=np.float32)
        pcm = torch.from_numpy(waveform).unsqueeze(0).to(torch.float32)
        if sample_rate != SAMPLE_RATE:
            pcm = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=SAMPLE_RATE)(pcm)
        min_samples = int(SAMPLE_RATE * 0.025)
        if pcm.shape[-1] < min_samples:
            pcm = F.pad(pcm, (0, min_samples - pcm.shape[-1]))
        pcm = pcm.to(self.device)
        feat = kaldi.fbank(
            pcm,
            num_mel_bins=80,
            frame_length=25,
            frame_shift=10,
            sample_frequency=SAMPLE_RATE,
            window_type="hamming",
        )
        feat = feat - torch.mean(feat, dim=0)
        feat = feat.unsqueeze(0)
        with torch.no_grad():
            outputs = self.model(feat)
            outputs = outputs[-1] if isinstance(outputs, tuple) else outputs
        vector = outputs[0].detach().cpu().numpy().astype(np.float32)
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector

    def _resolve_model_dir(self) -> Path:
        model_dir = self.cache_dir / self.model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        required = {"avg_model.pt", "config.yaml"}
        if required.issubset({path.name for path in model_dir.iterdir()}):
            return model_dir
        asset_name = self.assets.get(self.model_name)
        if asset_name is None:
            raise ValueError(f"Unsupported WeSpeaker model: {self.model_name}")
        response = requests.get(
            "https://modelscope.cn/api/v1/datasets/wenet/wespeaker_pretrained_models/oss/tree",
            timeout=30,
        )
        response.raise_for_status()
        model_info = next(
            item for item in response.json()["Data"] if item["Key"] == asset_name
        )
        self._download_and_extract(model_info["Url"], model_dir)
        return model_dir

    def _download_and_extract(self, url: str, dest: Path) -> None:
        archive_name = url.split("?")[0].split("/")[-1]
        archive_path = dest / archive_name
        if not archive_path.exists():
            console.print(f"[cyan]downloading WeSpeaker model[/cyan] {self.model_name}")
            urlretrieve(url, archive_path)
        if archive_name.endswith((".tar.gz", ".tar")):
            with tarfile.open(archive_path) as archive:
                for member in archive:
                    if "/" not in member.name:
                        continue
                    file_name = os.path.basename(member.name)
                    source = archive.extractfile(member)
                    if source is None:
                        continue
                    (dest / file_name).write_bytes(source.read())
        elif archive_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as archive:
                root = os.path.commonpath(archive.namelist())
                for member in archive.namelist():
                    relative = os.path.relpath(member, start=root)
                    if "/" not in relative:
                        continue
                    target_name = os.path.basename(relative)
                    with archive.open(member) as source:
                        (dest / target_name).write_bytes(source.read())
        else:
            raise ValueError(f"Unsupported archive format: {archive_name}")

    def _load_model(self, model_dir: Path):
        config = yaml.safe_load((model_dir / "config.yaml").read_text())
        model = get_speaker_model(config["model"])(**config["model_args"])
        load_checkpoint(model, str(model_dir / "avg_model.pt"))
        model.eval()
        model.frontend_type = "fbank"
        return model


def create_backend(config: BackendConfig) -> EmbeddingBackend:
    if config.backend == "spectrum":
        return SpectrumBackend()
    if config.backend == "wespeaker":
        return WeSpeakerBackend(
            model_name=config.wespeaker_model,
            cache_dir=config.wespeaker_cache_dir,
            device=config.device,
        )
    raise ValueError(f"Unsupported backend: {config.backend}")
