"""Multi-photo 3D reconstruction that runs on the CPU.

Pipeline
  1. Structure from Motion (pycolmap) finds the camera position of every photo.
  2. The object is cut out of every photo (rembg, with a GrabCut fallback).
  3. An implicit visual hull is carved from the cut-outs and the known cameras,
     then turned into a smooth mesh with marching cubes.
  4. Vertex colors are projected back from the best-facing photos.
  5. The mesh is stood upright, centred and scaled to unit size.

Limits: a visual hull cannot see into hollow spaces, and SfM needs photos that
overlap and have texture. See README.md for the capture guide.
"""
import math
import os
import shutil

import numpy as np

GRID = {"draft": 96, "standard": 144, "fine": 208}
CARVE_MAX_SIDE = 800      # masks are reduced to this size while carving
PRUNE = 12.0              # carve pixels: voxels this far outside are dropped
BLOCK = 1_500_000         # points projected per step (bounds memory)
MIN_VIEWS = 4
MAX_VIEWS = 80


class ReconstructionError(Exception):
    pass


def available():
    """(ok, reason). Photo reconstruction needs a few optional packages."""
    try:
        import cv2  # noqa: F401
        import pycolmap  # noqa: F401
        import scipy.ndimage  # noqa: F401
        import skimage.measure  # noqa: F401
        import trimesh  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return False, f"Missing package: {e}"
    return True, ""


def _noop(msg, pct=None):
    pass


# ----------------------------------------------------------------------------
# images and masks
# ----------------------------------------------------------------------------
def _read_rgb(path):
    import cv2

    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ReconstructionError(f"Could not read {os.path.basename(path)}.")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


_rembg_session = None
_rembg_broken = False


def _mask_rembg(rgb):
    global _rembg_session
    import rembg
    from PIL import Image

    if _rembg_session is None:
        _rembg_session = rembg.new_session()
    m = rembg.remove(Image.fromarray(rgb), session=_rembg_session, only_mask=True)
    return np.array(m) > 127


def _mask_grabcut(rgb):
    import cv2

    h, w = rgb.shape[:2]
    scale = 640.0 / max(h, w) if max(h, w) > 640 else 1.0
    small = cv2.resize(rgb, (max(8, int(w * scale)), max(8, int(h * scale))), interpolation=cv2.INTER_AREA)
    hs, ws = small.shape[:2]
    rect = (int(ws * 0.08), int(hs * 0.08), int(ws * 0.84), int(hs * 0.84))
    m = np.zeros((hs, ws), np.uint8)
    cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), m, rect,
                np.zeros((1, 65)), np.zeros((1, 65)), 4, cv2.GC_INIT_WITH_RECT)
    fg = ((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD)).astype(np.uint8)
    return cv2.resize(fg, (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)


def _clean_mask(mask):
    """Remove specks and keep only the largest blob."""
    import cv2

    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return np.zeros(mask.shape, bool)
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return lab == k


def default_mask(rgb, index=0):
    """Object mask for one photo. Uses rembg, falls back to GrabCut."""
    global _rembg_broken
    if not _rembg_broken:
        try:
            return _clean_mask(_mask_rembg(rgb))
        except Exception as e:  # noqa: BLE001
            _rembg_broken = True
            print("rembg unavailable, using GrabCut instead:", repr(e))
    return _clean_mask(_mask_grabcut(rgb))


# ----------------------------------------------------------------------------
# cameras
# ----------------------------------------------------------------------------
def _project(pts, view):
    """World points (N,3) -> pixel u, v and depth z, in the photo's own pixels."""
    pc = pts @ view["R"].T + view["t"]
    z = pc[:, 2]
    zz = np.where(z > 1e-9, z, 1.0)
    x = pc[:, 0] / zz
    y = pc[:, 1] / zz
    m, p = view["model"], view["params"]
    if m == "SIMPLE_PINHOLE":
        f, cx, cy = p[:3]
        u, v = f * x + cx, f * y + cy
    elif m == "PINHOLE":
        fx, fy, cx, cy = p[:4]
        u, v = fx * x + cx, fy * y + cy
    elif m == "SIMPLE_RADIAL":
        f, cx, cy, k = p[:4]
        d = 1.0 + k * (x * x + y * y)
        u, v = f * x * d + cx, f * y * d + cy
    elif m == "RADIAL":
        f, cx, cy, k1, k2 = p[:5]
        r2 = x * x + y * y
        d = 1.0 + k1 * r2 + k2 * r2 * r2
        u, v = f * x * d + cx, f * y * d + cy
    elif m == "OPENCV":
        fx, fy, cx, cy, k1, k2, p1, p2 = p[:8]
        r2 = x * x + y * y
        rad = k1 * r2 + k2 * r2 * r2
        dx = 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
        dy = p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
        u, v = fx * (x + x * rad + dx) + cx, fy * (y + y * rad + dy) + cy
    else:
        raise ReconstructionError(f"Unsupported camera model: {m}")
    return u, v, z


def _views_from_reconstruction(rec):
    """{photo index: view dict} for every registered photo."""
    views = {}
    for image_id in rec.reg_image_ids():
        img = rec.images[image_id]
        cam = rec.cameras[img.camera_id]
        cfw = img.cam_from_world
        if callable(cfw):
            cfw = cfw()
        M = np.asarray(cfw.matrix(), dtype=np.float64)
        R, t = M[:, :3], M[:, 3]
        model = getattr(cam, "model_name", None)
        if not isinstance(model, str):
            model = cam.model.name
        views[int(os.path.splitext(img.name)[0])] = {
            "R": R,
            "t": t,
            "center": -R.T @ t,
            "axis": R.T @ np.array([0.0, 0.0, 1.0]),
            "model": model,
            "params": np.asarray(cam.params, dtype=np.float64),
            "w": int(cam.width),
            "h": int(cam.height),
        }
    return views


def _run_sfm(view_paths, work, progress):
    import pycolmap

    shutil.rmtree(work, ignore_errors=True)
    img_dir = os.path.join(work, "images")
    sparse = os.path.join(work, "sparse")
    os.makedirs(img_dir)
    os.makedirs(sparse)
    for i, p in enumerate(view_paths):
        shutil.copy(p, os.path.join(img_dir, f"{i:03d}.jpg"))
    db = os.path.join(work, "db.db")

    progress("Finding features in the photos", 6)
    pycolmap.extract_features(db, img_dir)
    progress("Matching photos to each other", 20)
    pycolmap.match_exhaustive(db)
    progress("Working out where each photo was taken", 32)
    recs = pycolmap.incremental_mapping(db, img_dir, sparse)
    if not recs:
        raise ReconstructionError(
            "Could not work out the camera positions. Take photos from many angles, "
            "with each photo overlapping the last by about two thirds, in steady light, "
            "with a textured background that does not move."
        )
    return max(recs.values(), key=lambda r: r.num_reg_images())


def _focus_point(views):
    """Point closest to every camera's optical axis, and the median distance to it."""
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for v in views:
        P = np.eye(3) - np.outer(v["axis"], v["axis"])
        A += P
        b += P @ v["center"]
    if np.linalg.cond(A) > 1e8:
        raise ReconstructionError("The cameras do not look at a common object. Walk around the object while taking photos.")
    x = np.linalg.solve(A, b)
    front = np.mean([np.dot(x - v["center"], v["axis"]) > 0 for v in views])
    if front < 0.7:
        raise ReconstructionError("The cameras do not look at a common object. Keep the object in the middle of every photo.")
    r = float(np.median([np.linalg.norm(v["center"] - x) for v in views]))
    return x, r


def _farthest_order(centers):
    c = np.asarray(centers)
    order = [0]
    d = np.linalg.norm(c - c[0], axis=1)
    for _ in range(len(c) - 1):
        i = int(np.argmax(d))
        order.append(i)
        d = np.minimum(d, np.linalg.norm(c - c[i], axis=1))
    return order


# ----------------------------------------------------------------------------
# carving
# ----------------------------------------------------------------------------
def _sample(img, u, v):
    """Bilinear lookup of img at float pixel coordinates (any number of points)."""
    import cv2

    n = u.size
    width = 2048
    rows = -(-n // width)
    pad = rows * width - n
    uu = np.pad(u.astype(np.float32), (0, pad)).reshape(rows, width)
    vv = np.pad(v.astype(np.float32), (0, pad)).reshape(rows, width)
    out = cv2.remap(img, uu, vv, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return out.reshape(n + pad, -1)[:n] if out.ndim == 3 else out.reshape(-1)[:n]


def _make_item(mask_full, view, path):
    """Signed-distance map (positive inside the object) at carving resolution."""
    import cv2

    h0, w0 = mask_full.shape
    cs = min(1.0, CARVE_MAX_SIDE / max(h0, w0))
    w, h = max(8, int(round(w0 * cs))), max(8, int(round(h0 * cs)))
    small = cv2.resize(mask_full.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA) > 0.5
    m = small.astype(np.uint8)
    inside = cv2.distanceTransform(m, cv2.DIST_L2, 3)
    outside = cv2.distanceTransform(1 - m, cv2.DIST_L2, 3)
    return {
        "sdf": (inside - outside).astype(np.float32),
        "mask_eroded": cv2.erode(m, np.ones((5, 5), np.uint8)).astype(np.float32),
        "cs": cs,
        "w": w,
        "h": h,
        "view": view,
        "path": path,
    }


def _carve(box_min, dims, s, items, order, tolerant, progress=None, pct_range=(0, 0), label="Carving the shape"):
    """Implicit visual hull. Returns a float32 volume, positive inside the object.

    Each photo gives a signed distance to its silhouette. The hull value is the
    smallest of them; with `tolerant`, the second smallest, which survives one
    bad cut-out. Voxels far outside are dropped early to save time.
    """
    nx, ny, nz = dims
    n = nx * ny * nz
    m1 = np.full(n, np.inf, np.float32)
    m2 = np.full(n, np.inf, np.float32)
    seen = np.zeros(n, np.uint8)
    active = np.arange(n, dtype=np.int64)
    box_min = np.asarray(box_min, dtype=np.float64)

    for step, vi in enumerate(order):
        if active.size == 0:
            break
        it = items[vi]
        view, sdf, cs, w, h = it["view"], it["sdf"], it["cs"], it["w"], it["h"]
        for start in range(0, active.size, BLOCK):
            idx = active[start:start + BLOCK]
            k = idx % nz
            j = (idx // nz) % ny
            i = idx // (ny * nz)
            pts = box_min + (np.stack([i, j, k], axis=1) + 0.5) * s
            u, v, z = _project(pts, view)
            uc, vc = u * cs, v * cs
            ok = (z > 1e-9) & (uc >= 0) & (uc <= w - 1) & (vc >= 0) & (vc <= h - 1)
            if not ok.any():
                continue
            sel = idx[ok]
            val = _sample(sdf, uc[ok], vc[ok])
            seen[sel] += 1
            c1 = m1[sel]
            c2 = m2[sel]
            m2[sel] = np.minimum(c2, np.maximum(c1, val))
            m1[sel] = np.minimum(c1, val)
        cur = m2 if tolerant else m1
        active = active[cur[active] > -PRUNE]
        if progress and pct_range[1] > pct_range[0]:
            p = pct_range[0] + (pct_range[1] - pct_range[0]) * (step + 1) / len(order)
            progress(f"{label} ({step + 1} of {len(order)} photos)", int(p))

    f = m2 if tolerant else m1
    need = max(3, int(math.ceil(0.6 * len(order))))
    f = np.where(seen >= need, f, -PRUNE)
    f = np.nan_to_num(f, nan=-PRUNE, posinf=-PRUNE, neginf=-PRUNE)
    f = np.clip(f, -PRUNE, PRUNE)
    return f.astype(np.float32).reshape(dims)


def _largest_blob_box(vol, box_min, s):
    """World-space bounding box of the largest occupied blob in a coarse volume."""
    from scipy import ndimage

    occ = vol > 0
    if occ.sum() < 5:
        raise ReconstructionError(
            "The object outlines from the different photos do not overlap. "
            "The object may not have been cut out properly, or the photos do not all show the same object."
        )
    lab, n = ndimage.label(occ)
    sizes = ndimage.sum(occ, lab, index=np.arange(1, n + 1))
    blob = lab == (1 + int(np.argmax(sizes)))
    ijk = np.argwhere(blob)
    lo = box_min + ijk.min(axis=0) * s
    hi = box_min + (ijk.max(axis=0) + 1) * s
    margin = 0.08 * float(np.max(hi - lo)) + 2 * s
    return lo - margin, hi + margin


# ----------------------------------------------------------------------------
# mesh, colors, orientation
# ----------------------------------------------------------------------------
def _mesh_from_volume(vol, box_min, s):
    import trimesh
    from skimage import measure

    if not (vol > 0).any():
        raise ReconstructionError("No solid shape was found. Check that the object is cut out correctly in the photos.")
    padded = np.pad(vol, 1, constant_values=-PRUNE)
    verts, faces, _, _ = measure.marching_cubes(padded, level=0.0, spacing=(s, s, s))
    verts = verts + (np.asarray(box_min) + (0.5 - 1.0) * s)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        mesh = max(parts, key=lambda m: len(m.faces))
    trimesh.smoothing.filter_taubin(mesh, iterations=10)
    # make sure normals point outwards
    if np.mean(np.einsum("ij,ij->i", mesh.vertex_normals, mesh.vertices - mesh.centroid)) < 0:
        mesh.invert()
    return mesh


def _smooth_colors(mesh, colors, passes=2):
    """Average each vertex color with its neighbours to hide seams between photos."""
    import scipy.sparse as sp

    n = len(mesh.vertices)
    e = mesh.edges_unique
    A = sp.coo_matrix((np.ones(len(e) * 2), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    deg = np.asarray(A.sum(axis=1)).ravel()
    out = colors.astype(np.float64)
    for _ in range(passes):
        out = (out + A @ out) / (1.0 + deg)[:, None]
    return out


def _neighbor_average(mesh, colors, valid, passes):
    """Spread colors over the mesh: fill vertices without a color, smooth the rest."""
    import scipy.sparse as sp

    n = len(mesh.vertices)
    e = mesh.edges_unique
    A = sp.coo_matrix((np.ones(len(e) * 2), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    colors = colors.copy()
    valid = valid.astype(np.float64)
    for _ in range(passes):
        w = A @ valid
        avg = (A @ (colors * valid[:, None])) / np.maximum(w, 1e-9)[:, None]
        fill = (valid == 0) & (w > 0)
        colors[fill] = avg[fill]
        valid = np.where(fill, 1.0, valid)
        if valid.min() > 0:
            break
    return colors


def _bake_colors(mesh, items, progress=None, pct_range=(0, 0)):
    verts = mesh.vertices
    normals = mesh.vertex_normals
    acc = np.zeros((len(verts), 3))
    wsum = np.zeros(len(verts))
    for n, it in enumerate(items):
        view = it["view"]
        rgb = _read_rgb(it["path"]).astype(np.float32)
        u, v, z = _project(verts, view)
        uc, vc = u * it["cs"], v * it["cs"]
        inside = (z > 1e-9) & (uc >= 1) & (uc <= it["w"] - 2) & (vc >= 1) & (vc <= it["h"] - 2)
        w = np.zeros(len(verts))
        if inside.any():
            on_object = _sample(it["mask_eroded"], uc[inside], vc[inside]) > 0.99
            d = view["center"] - verts[inside]
            d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
            cosang = np.einsum("ij,ij->i", normals[inside], d)
            w[inside] = np.clip(cosang, 0.0, 1.0) ** 4 * on_object
        sel = w > 1e-3
        if sel.any():
            col = _sample(rgb, u[sel], v[sel])
            acc[sel] += col * w[sel][:, None]
            wsum[sel] += w[sel]
        if progress and pct_range[1] > pct_range[0]:
            progress(f"Painting the colors ({n + 1} of {len(items)} photos)",
                     int(pct_range[0] + (pct_range[1] - pct_range[0]) * (n + 1) / len(items)))
    valid = wsum > 1e-6
    colors = np.full((len(verts), 3), 128.0)
    colors[valid] = acc[valid] / wsum[valid][:, None]
    colors = _neighbor_average(mesh, colors, valid, passes=12)
    # one light smoothing pass to hide seams between photos
    colors = _smooth_colors(mesh, colors, passes=2)
    return np.clip(colors, 0, 255).astype(np.uint8)


def _stand_upright(mesh, views, center):
    """Rotate so the cameras' orbit axis points up (+Y), then centre and scale to 1."""
    import trimesh

    C = np.array([v["center"] for v in views])
    Cc = C - C.mean(axis=0)
    _, sv, vt = np.linalg.svd(Cc, full_matrices=False)
    if sv[2] < 0.6 * sv[1]:  # cameras lie roughly on a plane: its normal is "up"
        up = vt[2]
        if np.dot(C.mean(axis=0) - center, up) < 0:
            up = -up
        mesh.apply_transform(trimesh.geometry.align_vectors(up, [0.0, 1.0, 0.0]))
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    mesh.apply_scale(1.0 / float(np.max(hi - lo)))
    return mesh


def _write_glb(mesh, colors, path):
    import trimesh

    rgba = np.concatenate([colors, np.full((len(colors), 1), 255, np.uint8)], axis=1)
    mesh.visual = trimesh.visual.ColorVisuals(mesh, vertex_colors=rgba)
    mesh.export(path)
    _fix_glb_material(path)


def _fix_glb_material(path):
    """Give the GLB a matte, non-metallic material so vertex colors look natural."""
    import json
    import struct

    with open(path, "rb") as f:
        data = f.read()
    magic, version, _ = struct.unpack("<4sII", data[:12])
    if magic != b"glTF":
        return
    jlen, jtype = struct.unpack("<II", data[12:20])
    doc = json.loads(data[20:20 + jlen].decode("utf-8"))
    rest = data[20 + jlen:]
    doc["materials"] = [{
        "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.85},
        "doubleSided": True,
    }]
    for m in doc.get("meshes", []):
        for prim in m.get("primitives", []):
            prim["material"] = 0
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js) + len(rest)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", version, total))
        f.write(struct.pack("<II", len(js), jtype))
        f.write(js)
        f.write(rest)


# ----------------------------------------------------------------------------
# main entry point
# ----------------------------------------------------------------------------
def reconstruct(view_paths, out_glb, work_dir, quality="standard", colors=True, progress=None, mask_fn=None):
    """Build a GLB from many photos of one object. Returns a dict with a short note."""
    progress = progress or _noop
    mask_fn = mask_fn or default_mask
    ok, why = available()
    if not ok:
        raise ReconstructionError(why)
    n = len(view_paths)
    if n < MIN_VIEWS:
        raise ReconstructionError(f"Add at least {MIN_VIEWS} photos. 20 to 60 gives the best result.")
    res = GRID.get(quality, GRID["standard"])

    # 1. camera positions
    rec = _run_sfm(view_paths, work_dir, progress)
    views = _views_from_reconstruction(rec)
    used = len(views)
    if used < max(MIN_VIEWS, int(0.3 * n)):
        raise ReconstructionError(
            f"Only {used} of {n} photos could be placed in 3D. Take more photos with a lot of overlap "
            "and keep the background still and well lit."
        )
    progress(f"Placed {used} of {n} photos in 3D", 40)

    # 2. cut the object out of each photo
    items = []
    skipped = 0
    for k, i in enumerate(sorted(views)):
        rgb = _read_rgb(view_paths[i])
        mask = mask_fn(rgb, i)
        frac = float(mask.mean())
        if not (0.003 < frac < 0.9):
            skipped += 1
        else:
            items.append(_make_item(mask, views[i], view_paths[i]))
        progress(f"Cutting the object out of the photos ({k + 1} of {used})", int(40 + 20 * (k + 1) / used))
    if len(items) < MIN_VIEWS:
        raise ReconstructionError(
            "The object could not be separated from the background in enough photos. "
            "Use a plain, contrasting background and keep the whole object in view."
        )
    vlist = [it["view"] for it in items]
    order = _farthest_order([v["center"] for v in vlist])
    tolerant = len(items) >= 8

    # 3. find where the object is, then carve it in detail
    focus, radius = _focus_point(vlist)
    half = 0.75 * radius
    cs_ = 2 * half / 64
    coarse = _carve(focus - half, (64, 64, 64), cs_, items, order, tolerant)
    lo, hi = _largest_blob_box(coarse, focus - half, cs_)
    extent = hi - lo
    s = float(np.max(extent)) / res
    dims = tuple(int(math.ceil(e / s)) for e in extent)
    vol = _carve(lo, dims, s, items, order, tolerant, progress, (60, 85))

    # 4. mesh
    progress("Building the surface", 86)
    mesh = _mesh_from_volume(vol, lo, s)
    if len(mesh.faces) < 50:
        raise ReconstructionError("The reconstructed shape is too small. Check the photos and try again.")

    # 5. colors
    if colors:
        col = _bake_colors(mesh, items, progress, (88, 96))
    else:
        col = np.full((len(mesh.vertices), 3), 200, np.uint8)

    # 6. orientation, size, file
    progress("Saving the model", 97)
    _stand_upright(mesh, vlist, focus)
    os.makedirs(os.path.dirname(os.path.abspath(out_glb)), exist_ok=True)
    _write_glb(mesh, col, out_glb)
    shutil.rmtree(work_dir, ignore_errors=True)

    note = f"Built from {len(items)} of {n} photos."
    if len(items) < 0.6 * n:
        note += " Several photos could not be used. More overlap and steadier light will help."
    return {"note": note, "used": len(items), "total": n, "skipped_masks": skipped}
