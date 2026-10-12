import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "TripoSR"))

import numpy as np
import torch
import rembg
from PIL import Image
from tsr.system import TSR
from tsr.utils import remove_background, resize_foreground, to_gradio_3d_orientation

if not torch.cuda.is_available():
    raise RuntimeError("No CUDA GPU found. Use MODE=hf instead.")

device = "cuda:0"
model = TSR.from_pretrained(
    "stabilityai/TripoSR",
    config_name="config.yaml",
    weight_name="model.ckpt",
)
model.renderer.set_chunk_size(8192)
model.to(device)
rembg_session = rembg.new_session()


def generate(image_path, out_path, foreground_ratio=0.85, mc_resolution=256):
    image = Image.open(image_path).convert("RGB")
    image = remove_background(image, rembg_session)
    image = resize_foreground(image, foreground_ratio)
    arr = np.array(image).astype(np.float32) / 255.0
    arr = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
    image = Image.fromarray((arr * 255.0).astype(np.uint8))

    with torch.no_grad():
        scene_codes = model([image], device=device)
    mesh = model.extract_mesh(scene_codes, True, resolution=mc_resolution)[0]
    mesh = to_gradio_3d_orientation(mesh)
    mesh.export(out_path)
