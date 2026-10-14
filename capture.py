"""Live capture sessions: a phone sends photos to the PC while it shows which sides are still needed.

Two apps share this module:
  * the normal app (main.py, localhost only) creates sessions and builds models from them,
  * `capture_app` (HTTPS, reachable from the phone) only offers a few routes, each
    protected by the session's secret token.
"""
import io
import os
import secrets
import shutil
import threading
import time

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image, ImageOps

RINGS, SECTORS = 3, 18
MIN_PHOTOS, MAX_PHOTOS = 4, 80
MAX_BYTES = 8 * 1024 * 1024
TTL = 6 * 3600
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_lock = threading.Lock()
_sessions = {}
_cfg = {
    "host": None,
    "port": 8443,
    "listener": False,
    "reason": "Start the app with the launcher (serve.py) to enable live capture.",
}


# ---------------------------------------------------------------- setup
def configure(host, port, listener, reason=""):
    _cfg.update(host=host, port=port, listener=bool(listener), reason=reason)


def status():
    """(available, reason) for the PC page."""
    if not _cfg["listener"]:
        return False, _cfg["reason"]
    if not _cfg["host"] or _cfg["host"].startswith("127."):
        return False, "Could not find this PC's network address. Connect to Wi-Fi, or set CAPTURE_HOST to the address your phone can reach."
    return True, ""


# ---------------------------------------------------------------- sessions
def _dir(sid):
    return os.path.join("outputs", f"cap_{sid}")


def _cleanup():
    now = time.time()
    for sid in [k for k, v in _sessions.items() if now - v["created"] > TTL]:
        shutil.rmtree(_dir(sid), ignore_errors=True)
        _sessions.pop(sid, None)


def create():
    with _lock:
        _cleanup()
        sid = secrets.token_hex(4)
        s = {
            "id": sid,
            "token": secrets.token_urlsafe(16),
            "created": time.time(),
            "phone_seen": 0.0,
            "finished": False,
            "built": False,
            "photos": [],
            "next_n": 0,
        }
        os.makedirs(_dir(sid), exist_ok=True)
        _sessions[sid] = s
        return s


def get(sid):
    with _lock:
        return _sessions.get(sid)


def by_token(token):
    with _lock:
        for s in _sessions.values():
            if secrets.compare_digest(s["token"], token):
                return s
    return None


def cells(s):
    grid = [[0] * SECTORS for _ in range(RINGS)]
    for p in s["photos"]:
        grid[p["ring"]][p["sector"]] += 1
    return grid


def state(s, for_pc=False):
    grid = cells(s)
    covered = sum(1 for r in grid for c in r if c > 0)
    out = {
        "id": s["id"],
        "rings": RINGS,
        "sectors": SECTORS,
        "cells": grid,
        "count": len(s["photos"]),
        "covered": covered,
        "total": RINGS * SECTORS,
        "min": MIN_PHOTOS,
        "max": MAX_PHOTOS,
        "finished": s["finished"],
        "built": s["built"],
        "phone": (time.time() - s["phone_seen"]) < 8,
    }
    if for_pc:
        out["photos"] = [
            {"n": p["n"], "ring": p["ring"], "sector": p["sector"], "az": p["az"], "el": p["el"],
             "url": f"/outputs/cap_{s['id']}/{p['n']:03d}_t.jpg"}
            for p in s["photos"]
        ]
    return out


def touch(s):
    s["phone_seen"] = time.time()


def add_photo(s, data, az, el, ring, sector):
    if s["built"]:
        raise HTTPException(409, "This session was already used to build a model.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is too large.")
    if not (0 <= ring < RINGS and 0 <= sector < SECTORS):
        raise HTTPException(400, "Invalid area.")
    with _lock:
        if len(s["photos"]) >= MAX_PHOTOS:
            raise HTTPException(409, f"The limit is {MAX_PHOTOS} photos.")
        n = s["next_n"]
        s["next_n"] += 1
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        raise HTTPException(400, "That is not a valid image.")
    if min(img.size) < 320:
        raise HTTPException(400, "Photo is too small.")
    d = _dir(s["id"])
    os.makedirs(d, exist_ok=True)
    img.thumbnail((1600, 1600))
    img.save(os.path.join(d, f"{n:03d}.jpg"), quality=92)
    t = img.copy()
    t.thumbnail((160, 160))
    t.save(os.path.join(d, f"{n:03d}_t.jpg"), quality=80)
    with _lock:
        s["photos"].append({"n": n, "ring": ring, "sector": sector, "az": round(az, 1), "el": round(el, 1)})
    touch(s)
    return n


def delete_photo(s, n):
    with _lock:
        before = len(s["photos"])
        s["photos"] = [p for p in s["photos"] if p["n"] != n]
        if len(s["photos"]) == before:
            return False
    for suffix in (".jpg", "_t.jpg"):
        try:
            os.remove(os.path.join(_dir(s["id"]), f"{n:03d}{suffix}"))
        except OSError:
            pass
    return True


def photo_paths(s):
    return [os.path.join(_dir(s["id"]), f"{p['n']:03d}.jpg") for p in sorted(s["photos"], key=lambda p: p["n"])]


def mark_built(s):
    """Photos were handed to a build job. Keep the session so the phone can show 'Building'."""
    s["built"] = True
    shutil.rmtree(_dir(s["id"]), ignore_errors=True)


def remove(sid):
    with _lock:
        _sessions.pop(sid, None)
    shutil.rmtree(_dir(sid), ignore_errors=True)


def pc_info(s):
    """What the PC page needs to show the QR code."""
    import segno

    url = f"https://{_cfg['host']}:{_cfg['port']}/c/{s['token']}"
    qr = segno.make(url, error="m").svg_data_uri(scale=6, border=2, dark="#22302B")
    return {"id": s["id"], "url": url, "qr": qr, "state": state(s, True)}


# ---------------------------------------------------------------- phone app
capture_app = FastAPI(title="img23d phone capture", docs_url=None, redoc_url=None, openapi_url=None)
NO_STORE = {"Cache-Control": "no-store"}


def _session(token):
    s = by_token(token)
    if not s:
        raise HTTPException(404, "This capture link is not valid. Start a new live capture on your PC.")
    return s


@capture_app.get("/c/{token}")
def phone_page(token: str):
    _session(token)
    with open(os.path.join(STATIC, "capture.html"), encoding="utf-8") as f:
        html = f.read().replace("__TOKEN__", token)
    return HTMLResponse(html, headers=NO_STORE)


@capture_app.get("/c/{token}/dome.js")
def phone_dome(token: str):
    _session(token)
    return FileResponse(os.path.join(STATIC, "dome.js"), media_type="text/javascript", headers=NO_STORE)


@capture_app.get("/c/{token}/api/state")
def phone_state(token: str):
    s = _session(token)
    touch(s)
    return state(s)


@capture_app.post("/c/{token}/api/photo")
def phone_photo(
    token: str,
    file: UploadFile,
    az: float = Form(0.0),
    el: float = Form(0.0),
    ring: int = Form(...),
    sector: int = Form(...),
):
    s = _session(token)
    add_photo(s, file.file.read(MAX_BYTES + 1), az, el, ring, sector)
    return state(s)


@capture_app.post("/c/{token}/api/finish")
def phone_finish(token: str):
    s = _session(token)
    if len(s["photos"]) < MIN_PHOTOS:
        raise HTTPException(400, f"Take at least {MIN_PHOTOS} photos first.")
    s["finished"] = True
    touch(s)
    return state(s)
