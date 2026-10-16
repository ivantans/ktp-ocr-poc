"""
OCR foto KTP dengan PaddleOCR-VL-1.6.

    python ktp_ocr.py foto-ktp.jpg
    python ktp_ocr.py folder-foto/ --out results/uji-1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ktp_parser import parse_ktp

MODEL_ID = "PaddlePaddle/PaddleOCR-VL-1.6"


def pick_device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(device: str):
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    dtype = {"cpu": torch.float32, "mps": torch.float16}.get(device, torch.bfloat16)
    # bf16 hanya native mulai Ampere
    if device == "cuda" and torch.cuda.get_device_capability()[0] < 8:
        dtype = torch.float16
    model = (
        AutoModelForImageTextToText.from_pretrained(MODEL_ID, dtype=dtype)
        .to(device)
        .eval()
    )
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    return model, processor


def read_text(model, processor, image_path: str, max_new_tokens: int) -> str:
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "OCR:"},
            ],
        }
    ]
    # transformers 5.x: min_pixels pindah ke size.shortest_edge
    image_processor = processor.image_processor
    min_pixels = getattr(image_processor, "min_pixels", None) or image_processor.size.shortest_edge
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        images_kwargs={
            "size": {
                "shortest_edge": min_pixels,
                "longest_edge": 1280 * 28 * 28,
            }
        },
    ).to(model.device)
    # cache mati di generation_config bawaan model
    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, use_cache=True)
    return processor.decode(outputs[0][inputs["input_ids"].shape[-1] : -1])


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def collect_images(paths: list[str]) -> list[Path]:
    images: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            images += sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        else:
            images.append(path)
    return images


def summarize(results: list[dict]) -> dict:
    total = len(results)
    if total == 0:
        return {"images": 0}

    def share(predicate) -> str:
        return f"{sum(1 for r in results if predicate(r)) / total:.0%}"

    def verified(r: dict) -> bool:
        c = r["nikChecks"]
        return bool(r["fields"].get("nik")) and all(
            c.get(k) is True for k in ("format", "province", "birthDate", "gender", "serial")
        )

    def any_failed(r: dict) -> bool:
        return any(v is False for v in r["nikChecks"].values())

    empty_fields: dict[str, int] = {}
    for r in results:
        for key, value in r["fields"].items():
            if not value:
                empty_fields[key] = empty_fields.get(key, 0) + 1
    seconds = sorted(r["ocrSeconds"] for r in results)
    return {
        "images": total,
        "nikRead": share(lambda r: r["fields"].get("nik")),
        "nikFullyVerified": share(verified),
        "nikFailedACheck": share(any_failed),
        "birthDateMatchesNik": share(lambda r: r["nikChecks"].get("birthDate") is True),
        "genderMatchesNik": share(lambda r: r["nikChecks"].get("gender") is True),
        "emptyFieldCounts": dict(sorted(empty_fields.items(), key=lambda kv: -kv[1])),
        "secondsMedian": seconds[len(seconds) // 2],
        "secondsMax": seconds[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR KTP dengan PaddleOCR-VL-1.6")
    parser.add_argument("images", nargs="+", help="foto KTP atau folder berisi foto KTP")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "mps", "cuda"])
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--show-text", action="store_true", help="sertakan teks mentah OCR")
    parser.add_argument(
        "--out",
        help="folder hasil; berisi satu JSON per foto (dengan teks mentah) dan summary.json",
    )
    args = parser.parse_args()

    images = collect_images(args.images)
    if not images:
        print("tidak ada foto yang ditemukan", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    device = pick_device(args.device)
    started = time.perf_counter()
    model, processor = load_model(device)
    load_seconds = round(time.perf_counter() - started, 1)
    print(f"model dimuat di {device} dalam {load_seconds} detik", file=sys.stderr)

    results: list[dict] = []
    for index, path in enumerate(images, start=1):
        started = time.perf_counter()
        try:
            text = read_text(model, processor, str(path), args.max_new_tokens)
        except Exception as error:  # satu foto bermasalah tidak menghentikan sisanya
            print(f"[{index}/{len(images)}] {path.name}: GAGAL {error}", file=sys.stderr)
            continue
        result = parse_ktp(text).to_dict()
        result["image"] = str(path)
        result["device"] = device
        result["ocrSeconds"] = round(time.perf_counter() - started, 2)
        results.append(result)

        if out_dir:
            (out_dir / f"{path.stem}.json").write_text(
                json.dumps({**result, "rawText": text}, ensure_ascii=False, indent=2)
            )
            status = (
                "NIK gagal pemeriksaan"
                if any(v is False for v in result["nikChecks"].values())
                else "NIK terverifikasi"
                if result["fields"].get("nik")
                and all(v is True for v in result["nikChecks"].values())
                else "perlu dicek"
            )
            print(
                f"[{index}/{len(images)}] {path.name}: {result['ocrSeconds']} detik, {status}",
                file=sys.stderr,
            )
        else:
            if args.show_text:
                result["rawText"] = text
            print(json.dumps(result, ensure_ascii=False, indent=2))

    summary = summarize(results)
    if out_dir:
        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    if len(images) > 1 or out_dir:
        print(json.dumps({"summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
