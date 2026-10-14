import os
import re
import threading
import time

MODE = os.environ.get("MODE", "hf").lower()
HF_TOKEN = os.environ.get("HF_TOKEN") or None

SPACES = {
    "sf3d": "stabilityai/stable-fast-3d",
    "triposr": "stabilityai/TripoSR",
}
LABELS = {
    "auto": "Auto",
    "sf3d": "Stable Fast 3D",
    "triposr": "TripoSR",
    "local": "TripoSR on this GPU",
    "photogrammetry": "Photogrammetry",
}
DETAIL = {"low": 160, "medium": 256, "high": 320}

if MODE == "local":
    from local_triposr import generate as _local_generate  # loads the model once
else:
    from gradio_client import Client, handle_file

_clients = {}
_lock = threading.Lock()


class EngineError(Exception):
    pass


def available():
    if MODE == "local":
        return [{"id": "local", "label": LABELS["local"]}]
    return [
        {"id": "auto", "label": "Auto: best available"},
        {"id": "sf3d", "label": LABELS["sf3d"]},
        {"id": "triposr", "label": LABELS["triposr"]},
    ]


def _client(key):
    with _lock:
        if key not in _clients:
            _clients[key] = Client(SPACES[key], token=HF_TOKEN, verbose=False)
        return _clients[key]


def _drop_client(key):
    with _lock:
        _clients.pop(key, None)


def _paths(result):
    items = result if isinstance(result, (list, tuple)) else [result]
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            p = it.get("path") or it.get("value")
            if isinstance(p, dict):
                p = p.get("path")
            if isinstance(p, str):
                out.append(p)
    return out


def _glb_from(result):
    for p in _paths(result):
        if p.lower().endswith(".glb"):
            return p
    raise EngineError("The engine did not return a GLB file.")


def _run_sf3d(img_path, o, progress):
    c = _client("sf3d")
    progress("Building the model on Stable Fast 3D")
    res = c.predict(
        input_image=handle_file(img_path),
        foreground_ratio=o["foreground_ratio"],
        remesh_option=o["remesh"],
        vertex_count=-1,
        texture_size=o["texture_size"],
        api_name="/run_button",
    )
    return _glb_from(res)


def _run_triposr(img_path, o, progress):
    c = _client("triposr")
    progress("Removing the background")
    pre = _paths(c.predict(handle_file(img_path), True, o["foreground_ratio"], api_name="/preprocess"))
    if not pre:
        raise EngineError("TripoSR did not return a processed image.")
    progress("Building the model on TripoSR")
    res = c.predict(handle_file(pre[0]), DETAIL.get(o["mesh_detail"], 256), api_name="/generate")
    return _glb_from(res)


def _run_local(img_path, o, progress):
    out = img_path.rsplit(".", 1)[0] + "_local.glb"
    progress("Building the model on your GPU")
    _local_generate(
        img_path,
        out,
        foreground_ratio=o["foreground_ratio"],
        mc_resolution=DETAIL.get(o["mesh_detail"], 256),
    )
    return out


RUNNERS = {"sf3d": None, "triposr": None, "local": None}
if MODE == "local":
    RUNNERS["local"] = _run_local
else:
    RUNNERS["sf3d"] = _run_sf3d
    RUNNERS["triposr"] = _run_triposr


def _friendly(e):
    msg = str(e)
    low = msg.lower()
    m = re.search(r"try again in [0-9:]+", low)
    if "quota" in low or m:
        tail = (" " + m.group(0).capitalize() + ".") if m else ""
        return "The free GPU quota is used up." + tail + " Add a Hugging Face token to get more (see README)."
    if "upstream gradio app has raised" in low or "verbose error" in low:
        return "The free GPU service failed on this image or is busy. Try again, or use a simpler image."
    if "api_name" in low or "cannot find a function" in low:
        return "The online model changed its interface. Try the other engine, or update engines.py."
    if any(k in low for k in ("connect", "timed out", "timeout", "resolve", "name or service", "network")):
        return "Could not reach the model service. Check your internet connection."
    return msg[:300] or "Unknown error."


def run(engine, img_path, opts, progress):
    """Returns (glb_path, engine_key_used)."""
    if MODE == "local":
        order = ["local"]
    elif engine == "auto":
        order = ["sf3d", "triposr"]
    elif engine in RUNNERS and RUNNERS[engine]:
        order = [engine]
    else:
        raise EngineError("Unknown engine.")

    last = None
    for idx, key in enumerate(order):
        for attempt in (1, 2):
            try:
                return RUNNERS[key](img_path, opts, progress), key
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"[{key}] attempt {attempt} failed: {e!r}")
                _drop_client(key)
                if "quota" in str(e).lower():
                    break
                if attempt == 1:
                    progress(f"{LABELS[key]} failed, retrying")
                    time.sleep(3)
        if idx < len(order) - 1:
            progress(f"{LABELS[key]} failed, switching engine")
    raise EngineError(_friendly(last))
