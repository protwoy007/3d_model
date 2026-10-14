import io
import json
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

import capture
import engines
import photogrammetry
import store

MODE = engines.MODE
MAX_UPLOAD = 10 * 1024 * 1024
MAX_PHOTO = 15 * 1024 * 1024      # per photo in multi-photo mode
MIN_PHOTOS = photogrammetry.MIN_VIEWS
MAX_PHOTOS = photogrammetry.MAX_VIEWS

os.makedirs("outputs", exist_ok=True)
os.makedirs("static", exist_ok=True)
store.init()

# One job at a time: free GPU spaces have small quotas.
executor = ThreadPoolExecutor(max_workers=1)
app = FastAPI(title="img23d")


# ---------- helpers ----------
def mesh_stats(path):
    out = {"size_kb": max(1, os.path.getsize(path) // 1024)}
    try:
        import trimesh

        m = trimesh.load(path, force="mesh")
        out["vertices"] = int(len(m.vertices))
        out["faces"] = int(len(m.faces))
    except Exception as e:  # noqa: BLE001
        print("mesh stats failed:", repr(e))
    return out


def public(row):
    d = dict(row)
    d["options"] = json.loads(d.get("options") or "{}")
    jid = d["id"]
    d["thumb_url"] = f"/outputs/{jid}_thumb.jpg"
    d["glb_url"] = f"/outputs/{jid}.glb" if d["status"] == "done" else None
    d["duration"] = (
        round(d["finished"] - d["started"], 1)
        if d["status"] == "done" and d.get("started") and d.get("finished")
        else None
    )
    key = d.get("engine_used") or d.get("engine")
    d["engine_label"] = engines.LABELS.get(key, key)
    d["ahead"] = store.queued_ahead(jid) if d["status"] == "queued" else 0
    return d


def process(job_id, opts):
    job = store.get_job(job_id)
    if not job:
        return
    store.update_job(job_id, status="processing", stage="Starting", started=time.time())

    def progress(msg, pct=None):
        if pct is None:
            store.update_job(job_id, stage=msg)
        else:
            store.update_job(job_id, stage=msg, progress=int(pct))

    try:
        glb = f"outputs/{job_id}.glb"
        extra = {}
        if job["kind"] == "multi":
            views_dir = f"outputs/{job_id}_views"
            paths = sorted(
                os.path.join(views_dir, f) for f in os.listdir(views_dir) if f.lower().endswith(".jpg")
            )
            info = photogrammetry.reconstruct(
                paths,
                glb,
                f"outputs/{job_id}_work",
                quality=opts.get("quality", "standard"),
                colors=bool(opts.get("colors", True)),
                progress=progress,
            )
            used = "photogrammetry"
            extra["note"] = info["note"]
        else:
            src, used = engines.run(job["engine"], f"outputs/{job_id}.png", opts, progress)
            if not store.get_job(job_id):  # deleted while running
                return
            shutil.copy(src, glb)
        if not store.get_job(job_id):
            return
        stats = mesh_stats(glb)
        store.update_job(
            job_id, status="done", stage="Done", engine_used=used, finished=time.time(),
            progress=100, **stats, **extra
        )
    except Exception as e:  # noqa: BLE001
        print("job failed:", repr(e))
        shutil.rmtree(f"outputs/{job_id}_work", ignore_errors=True)
        msg = str(e) if isinstance(e, (photogrammetry.ReconstructionError, engines.EngineError)) else (str(e) or "Unexpected error.")
        store.update_job(job_id, status="failed", stage="Failed", error=msg[:400], finished=time.time())


# ---------- API ----------
_mv_status = None


def photogrammetry_status():
    global _mv_status
    if _mv_status is None or not _mv_status[0]:
        _mv_status = photogrammetry.available()
    return _mv_status


@app.get("/config")
@app.get("/api/config")
def config():
    ok, reason = photogrammetry_status()
    return {
        "mode": MODE,
        "engines": engines.available(),
        "token": bool(engines.HF_TOKEN),
        "multiview": {"available": ok, "reason": reason, "min": MIN_PHOTOS, "max": MAX_PHOTOS},
        "capture": dict(zip(("available", "reason"), capture.status())),
    }


@app.post("/api/jobs")
def create_job(
    file: UploadFile,
    engine: str = Form("auto"),
    foreground_ratio: float = Form(0.85),
    remesh: str = Form("None"),
    texture_size: int = Form(1024),
    mesh_detail: str = Form("medium"),
):
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "That image is over 10 MB. Choose a smaller one.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img = ImageOps.exif_transpose(img).convert("RGBA")
    except Exception:
        raise HTTPException(400, "That file is not a valid image.")

    if remesh not in ("None", "Triangle", "Quad"):
        remesh = "None"
    if texture_size not in (512, 1024, 2048):
        texture_size = 1024
    if mesh_detail not in engines.DETAIL:
        mesh_detail = "medium"
    foreground_ratio = min(1.0, max(0.5, foreground_ratio))
    if engine != "auto" and engine not in [e["id"] for e in engines.available()]:
        raise HTTPException(400, "Unknown engine.")

    job_id = uuid.uuid4().hex[:12]
    img.thumbnail((1024, 1024))
    img.save(f"outputs/{job_id}.png")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, mask=img.split()[3])
    bg.thumbnail((360, 360))
    bg.save(f"outputs/{job_id}_thumb.jpg", quality=85)

    opts = {
        "foreground_ratio": foreground_ratio,
        "remesh": remesh,
        "texture_size": texture_size,
        "mesh_detail": mesh_detail,
    }
    store.create_job(job_id, file.filename or "image", engine, json.dumps(opts))
    executor.submit(process, job_id, opts)
    return {"id": job_id}


def queue_multi(prepared, quality, colors):
    """Save the photos of one object and queue a reconstruction. Returns the job id."""
    job_id = uuid.uuid4().hex[:12]
    views = f"outputs/{job_id}_views"
    os.makedirs(views, exist_ok=True)
    for i, img in enumerate(prepared):
        img.thumbnail((1600, 1600))
        img.save(f"{views}/{i:03d}.jpg", quality=93)
    thumb = prepared[0].copy()
    thumb.thumbnail((360, 360))
    thumb.save(f"outputs/{job_id}_thumb.jpg", quality=85)

    opts = {"quality": quality, "colors": bool(colors)}
    store.create_job(
        job_id, f"{len(prepared)} photos", "photogrammetry", json.dumps(opts),
        kind="multi", image_count=len(prepared),
    )
    executor.submit(process, job_id, opts)
    return job_id


@app.post("/api/jobs/multi")
def create_multi_job(
    files: list[UploadFile],
    quality: str = Form("standard"),
    colors: bool = Form(True),
):
    ok, reason = photogrammetry_status()
    if not ok:
        raise HTTPException(
            400,
            "Multi-photo mode needs extra packages (" + reason + "). "
            "Close the app, run the launcher again to install them, then retry.",
        )
    if len(files) < MIN_PHOTOS:
        raise HTTPException(400, f"Add at least {MIN_PHOTOS} photos. 20 to 60 gives the best result.")
    if len(files) > MAX_PHOTOS:
        raise HTTPException(400, f"Too many photos. The limit is {MAX_PHOTOS}.")
    if quality not in photogrammetry.GRID:
        quality = "standard"

    prepared = []
    for n, f in enumerate(files, start=1):
        data = f.file.read(MAX_PHOTO + 1)
        label = f"Photo {n} ({f.filename or 'unnamed'})"
        if len(data) > MAX_PHOTO:
            raise HTTPException(413, f"{label} is over 15 MB.")
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
            img = ImageOps.exif_transpose(img).convert("RGB")
        except Exception:
            raise HTTPException(400, f"{label} is not a valid image.")
        if min(img.size) < 320:
            raise HTTPException(400, f"{label} is too small. Use photos at least 640 pixels wide.")
        prepared.append(img)

    return {"id": queue_multi(prepared, quality, colors)}


# ---------- live capture from a phone (PC side) ----------
def _capture_session(sid):
    s = capture.get(sid)
    if not s:
        raise HTTPException(404, "This live capture session no longer exists.")
    return s


@app.post("/api/capture")
def capture_start():
    ok, reason = capture.status()
    if not ok:
        raise HTTPException(400, reason)
    ok, reason = photogrammetry_status()
    if not ok:
        raise HTTPException(400, "Many-photo mode needs extra packages (" + reason + "). Run the launcher again to install them.")
    return capture.pc_info(capture.create())


@app.get("/api/capture/{sid}")
def capture_state(sid: str):
    return capture.state(_capture_session(sid), for_pc=True)


@app.delete("/api/capture/{sid}/photos/{n}")
def capture_delete_photo(sid: str, n: int):
    s = _capture_session(sid)
    if not capture.delete_photo(s, n):
        raise HTTPException(404, "Photo not found.")
    return capture.state(s, for_pc=True)


@app.post("/api/capture/{sid}/build")
def capture_build(sid: str, quality: str = Form("standard"), colors: bool = Form(True)):
    s = _capture_session(sid)
    paths = capture.photo_paths(s)
    if len(paths) < MIN_PHOTOS:
        raise HTTPException(400, f"Take at least {MIN_PHOTOS} photos first. 20 to 60 gives the best result.")
    if quality not in photogrammetry.GRID:
        quality = "standard"
    prepared = []
    for p in paths:
        img = Image.open(p)
        img.load()
        prepared.append(img.convert("RGB"))
    job_id = queue_multi(prepared, quality, colors)
    capture.mark_built(s)
    return {"id": job_id}


@app.delete("/api/capture/{sid}")
def capture_cancel(sid: str):
    capture.remove(sid)
    return {"ok": True}


@app.get("/api/jobs")
def list_jobs():
    return [public(r) for r in store.list_jobs()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(404, "Job not found.")
    return public(row)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    if not store.get_job(job_id):
        raise HTTPException(404, "Job not found.")
    store.delete_job(job_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/download/{fmt}")
def download(job_id: str, fmt: str):
    row = store.get_job(job_id)
    if not row or row["status"] != "done":
        raise HTTPException(404, "Model not found.")
    glb = f"outputs/{job_id}.glb"
    if fmt == "glb":
        return FileResponse(glb, media_type="model/gltf-binary", filename=f"model-{job_id}.glb")
    if fmt in ("stl", "obj"):
        out = f"outputs/{job_id}.{fmt}"
        if not os.path.exists(out):
            try:
                import trimesh

                m = trimesh.load(glb, force="mesh")
                if fmt == "stl":
                    m.export(out, file_type="stl")
                else:
                    try:
                        m.export(out, file_type="obj", include_texture=False, include_color=False)
                    except TypeError:
                        m.export(out, file_type="obj")
            except Exception as e:  # noqa: BLE001
                raise HTTPException(500, f"Could not convert the model: {e}")
        return FileResponse(out, filename=f"model-{job_id}.{fmt}")
    raise HTTPException(400, "Unknown format. Use glb, stl or obj.")


app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
