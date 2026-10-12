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

import engines
import store

MODE = engines.MODE
MAX_UPLOAD = 10 * 1024 * 1024

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

    def progress(msg):
        store.update_job(job_id, stage=msg)

    try:
        src, used = engines.run(job["engine"], f"outputs/{job_id}.png", opts, progress)
        if not store.get_job(job_id):  # deleted while running
            return
        glb = f"outputs/{job_id}.glb"
        shutil.copy(src, glb)
        stats = mesh_stats(glb)
        store.update_job(
            job_id, status="done", stage="Done", engine_used=used, finished=time.time(), **stats
        )
    except Exception as e:  # noqa: BLE001
        print("job failed:", repr(e))
        store.update_job(job_id, status="failed", stage="Failed", error=str(e), finished=time.time())


# ---------- API ----------
@app.get("/config")
@app.get("/api/config")
def config():
    return {"mode": MODE, "engines": engines.available(), "token": bool(engines.HF_TOKEN)}


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
