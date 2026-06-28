"""Run only Stable-Hair's stage-1 Bald Converter.

This script is a thin Hair App bridge around the upstream Stable-Hair repo. It
does not vendor Stable-Hair code or weights. Point it at a private Stable-Hair
checkout and a downloaded stage-1 checkpoint, then it writes bald-converted
private images for FaceBuilder texture-bake experiments.

Expected private checkout:

    private_outputs/third_party/Stable-Hair/

Expected checkpoint:

    <stable_hair_root>/models/stage1/pytorch_model.bin

The generated images are private biometric assets. Do not commit them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stable-hair-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-images", type=int, default=None)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--pretrained-model-path", default="runwayml/stable-diffusion-v1-5")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("float16", "float32"), default="float16")
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--guidance-scale", type=float, default=1.5)
    parser.add_argument("--converter-scale", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=-1)
    parser.add_argument(
        "--preserve-input-size",
        action="store_true",
        help="Resize the generated bald image back to each input image size.",
    )
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _list_inputs(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    paths.extend(args.input)
    if args.input_dir:
        paths.extend(
            path
            for path in sorted(args.input_dir.iterdir(), key=lambda p: p.name.lower())
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)
    if args.max_images is not None:
        return unique[: args.max_images]
    return unique


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class StableHairBaldOnly:
    """Minimal loader for Stable-Hair stage 1.

    Upstream `infer_full.py` loads both the stage-2 hair transfer pipeline and
    the stage-1 bald converter. Hair App only needs the stage-1 pipeline here.
    """

    def __init__(
        self,
        *,
        stable_hair_root: Path,
        checkpoint: Path,
        pretrained_model_path: str,
        device: str,
        dtype_name: str,
    ) -> None:
        stable_hair_root = stable_hair_root.resolve()
        checkpoint = checkpoint.resolve()
        if not stable_hair_root.exists():
            raise FileNotFoundError(f"Stable-Hair root not found: {stable_hair_root}")
        if not checkpoint.exists():
            raise FileNotFoundError(
                "Stable-Hair stage-1 checkpoint not found: "
                f"{checkpoint}\n"
                "Download the upstream pretrained models and place stage1 at "
                "<stable_hair_root>/models/stage1/pytorch_model.bin."
            )

        sys.path.insert(0, str(stable_hair_root))

        import torch
        from diffusers import UniPCMultistepScheduler
        from diffusers.models import UNet2DConditionModel
        from ref_encoder.latent_controlnet import ControlNetModel
        from utils.pipeline_cn import StableDiffusionControlNetPipeline

        dtype = torch.float16 if dtype_name == "float16" else torch.float32
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is False.")

        unet = UNet2DConditionModel.from_pretrained(pretrained_model_path, subfolder="unet").to(device)
        bald_converter = ControlNetModel.from_unet(unet).to(device)
        state_dict = torch.load(str(checkpoint), map_location=device)
        bald_converter.load_state_dict(state_dict, strict=False)
        bald_converter.to(dtype=dtype)
        del unet

        pipe = StableDiffusionControlNetPipeline.from_pretrained(
            pretrained_model_path,
            controlnet=bald_converter,
            safety_checker=None,
            torch_dtype=dtype,
        )
        pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)
        self.pipe = pipe.to(device)
        self.torch = torch
        self.device = device

    def convert(
        self,
        image: Image.Image,
        *,
        size: int,
        steps: int,
        guidance_scale: float,
        converter_scale: float,
        seed: int,
        preserve_input_size: bool,
    ) -> Image.Image:
        original_size = image.size
        work = image.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
        generator = None
        if seed >= 0:
            generator = self.torch.Generator(device=self.device)
            generator.manual_seed(seed)
        with self.torch.inference_mode():
            result = self.pipe(
                prompt="",
                negative_prompt="",
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
                width=work.width,
                height=work.height,
                image=work,
                controlnet_conditioning_scale=converter_scale,
                generator=generator,
            ).images[0]
        if preserve_input_size and result.size != original_size:
            result = result.resize(original_size, Image.Resampling.LANCZOS)
        return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    stable_hair_root = args.stable_hair_root.resolve()
    checkpoint = args.checkpoint or (stable_hair_root / "models" / "stage1" / "pytorch_model.bin")
    inputs = _list_inputs(args)
    if not inputs:
        raise SystemExit("No input images found.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    converter = StableHairBaldOnly(
        stable_hair_root=stable_hair_root,
        checkpoint=checkpoint,
        pretrained_model_path=args.pretrained_model_path,
        device=args.device,
        dtype_name=args.dtype,
    )

    rows: list[dict[str, Any]] = []
    for index, input_path in enumerate(inputs):
        with Image.open(input_path) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
        output_path = args.output_dir / f"{index:03d}_{input_path.stem}_stable_hair_bald.png"
        started = time.time()
        bald = converter.convert(
            image,
            size=args.size,
            steps=args.steps,
            guidance_scale=args.guidance_scale,
            converter_scale=args.converter_scale,
            seed=args.seed,
            preserve_input_size=args.preserve_input_size,
        )
        bald.save(output_path)
        rows.append(
            {
                "input": _safe_path(input_path),
                "output": _safe_path(output_path),
                "input_size": list(image.size),
                "output_size": list(bald.size),
                "duration_sec": time.time() - started,
            }
        )

    _write_json(
        args.output_dir / "stable_hair_bald_only_manifest.json",
        {
            "schema_version": "hair_app_stable_hair_bald_only_v1",
            "created_at_unix": time.time(),
            "stable_hair_root": _safe_path(stable_hair_root),
            "checkpoint": _safe_path(checkpoint),
            "pretrained_model_path": args.pretrained_model_path,
            "device": args.device,
            "dtype": args.dtype,
            "size": args.size,
            "steps": args.steps,
            "guidance_scale": args.guidance_scale,
            "converter_scale": args.converter_scale,
            "seed": args.seed,
            "preserve_input_size": args.preserve_input_size,
            "rows": rows,
        },
    )
    print(f"STABLE_HAIR_BALD_ONLY_OUTPUT {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
