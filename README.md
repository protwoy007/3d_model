# img23d

Turn a single photo into a 3D model in your browser. Upload an image, wait a minute, rotate the result, and download it as GLB, STL, or OBJ.

Built with FastAPI, SQLite, a plain HTML frontend, and [`<model-viewer>`](https://modelviewer.dev/) for the 3D preview.

## Features

- **Two engines in free mode:** Stable Fast 3D and TripoSR, both running on free Hugging Face GPUs.
- **Auto engine:** tries Stable Fast 3D first and switches to TripoSR if it fails. Each engine is retried once.
- **Compare mode:** builds the same photo with both engines and shows the results side by side with build time, vertex count, face count, and file size.
- **Job queue with live progress:** jobs run one at a time, and the page shows the queue position and current step.
- **History:** every model is saved in a local SQLite database. Reopen, download, or delete past models on the History tab.
- **Export formats:** GLB (with textures), STL for 3D printing, and OBJ (shape only).
- **Build options:** object size in frame, mesh detail, mesh style, and texture quality.
- **Readable errors:** quota problems, busy services, and network failures are explained in plain language.
- **GPU mode:** run TripoSR on your own NVIDIA GPU with no online service.

## Two ways to run it

| | Free mode | GPU mode |
|---|---|---|
| Launcher | `run_free.bat` | `run_gpu.bat` |
| Needs a GPU in your PC | No | Yes, NVIDIA with about 6 GB VRAM or more |
| Where the model runs | Free Hugging Face Spaces | Your own GPU (TripoSR) |
| Engines | Stable Fast 3D, TripoSR, Auto, Compare | TripoSR |
| Internet needed while using it | Yes | Only for the first setup |
| Speed | 30-90 seconds, slower when the Spaces are busy | A few seconds |
| Privacy | Images are sent to public Hugging Face Spaces | Images never leave your PC |
| First-run setup | A few minutes | 15-30 minutes |

## Quick start (Windows)

1. Download or clone this project and keep all files together in one folder.
2. Double-click the launcher you want:
   - **No GPU:** `run_free.bat`
   - **NVIDIA GPU:** `run_gpu.bat`
3. Your browser opens at `http://127.0.0.1:8000`. Choose an image and click **Build 3D model**.
4. Close the black terminal window to stop the server.

Each launcher sets everything up on the first run. Later runs start straight away.

## Using the app

1. **Create tab:** drop or choose an image. Open **Options** to change the engine and quality settings.
2. Tick **Compare both engines** to build the model twice and see both results next to each other.
3. Click **Build 3D model**. Drag the finished model to rotate it, and scroll to zoom.
4. Download **GLB** for the full model, **STL for printing** for 3D printers, or **OBJ, shape only** for geometry without textures.
5. **History tab:** every build is listed with its engine, build time, and size. Use **Open** to view it again or **Delete** to remove it and its files.

| Option | What it does | Applies to |
|---|---|---|
| Model engine | Auto, Stable Fast 3D, or TripoSR | Free mode |
| Object size in frame | How much of the image the object fills | Both engines |
| Mesh detail | Resolution of the extracted mesh | TripoSR |
| Mesh style | Original, clean triangles, or clean quads | Stable Fast 3D |
| Texture quality | 512, 1024, or 2048 px textures | Stable Fast 3D |

## What each launcher does

### `run_free.bat`
1. Checks that Python 3.10 or newer is installed.
2. Checks that the project files exist and creates the `outputs` folder.
3. Creates a virtual environment in `venv`.
4. Installs the packages from `requirements.txt`.
5. Asks for an optional Hugging Face token and saves it to `.hf_token` (see below).
6. Starts the server and opens your browser when it is ready.

### `run_gpu.bat`
1. Checks that an NVIDIA driver is installed (`nvidia-smi`).
2. Finds Python 3.10 or 3.11, or offers to install Python 3.11 with `winget`.
3. Checks for Git, or offers to install it with `winget`.
4. Downloads the TripoSR source code into the `TripoSR` folder.
5. Checks for the Visual Studio C++ Build Tools, or offers to install them with `winget`.
6. Checks for the CUDA Toolkit, or offers to install it with `winget` (optional).
7. Creates a separate virtual environment in `venv-gpu`.
8. Installs PyTorch with CUDA, the app packages from `requirements-gpu.txt`, the TripoSR packages, and compiles `torchmcubes`.
9. Verifies that PyTorch can see your GPU, then starts the server and opens your browser when it is ready.

The first GPU start also downloads the TripoSR model weights, so it takes a few minutes. After that it starts quickly.

## Hugging Face token (free mode)

The free Hugging Face Spaces give anonymous users a small GPU quota. A free token raises it and avoids most quota errors.

1. Make a free account at https://huggingface.co
2. Open https://huggingface.co/settings/tokens and create a token of type **Read**.
3. Paste it when `run_free.bat` asks. It is saved in `.hf_token` next to the launcher. This file is ignored by Git and is never uploaded.

To change the token, delete `.hf_token` and run the launcher again.

## Project structure

```
img23d/
  main.py               FastAPI server, job queue, and API
  engines.py            Stable Fast 3D, TripoSR, and local GPU engines with retry and fallback
  store.py              SQLite job history
  local_triposr.py      TripoSR inference code (GPU mode)
  static/
    index.html          Web interface
  requirements.txt      Packages for free mode
  requirements-gpu.txt  Packages for GPU mode
  run_free.bat          Launcher: no GPU
  run_gpu.bat           Launcher: NVIDIA GPU
  README.md
  .gitignore
```

Created on first run and ignored by Git: `venv/`, `venv-gpu/`, `outputs/` (images and models), `data/` (history database), `TripoSR/`, `.hf_token`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/config` | Mode, available engines, token status |
| POST | `/api/jobs` | Upload an image and queue a job. Form fields: `file`, `engine`, `foreground_ratio`, `mesh_detail`, `remesh`, `texture_size` |
| GET | `/api/jobs` | List history, newest first |
| GET | `/api/jobs/{id}` | Job status, stage, engine used, and mesh stats |
| DELETE | `/api/jobs/{id}` | Delete a job and its files |
| GET | `/api/jobs/{id}/download/{glb\|stl\|obj}` | Download a finished model |

Interactive API docs are available at `http://127.0.0.1:8000/docs` while the server runs.

## Configuration

| Setting | Where | Default | Purpose |
|---|---|---|---|
| `MODE` | set by the launchers | `hf` / `local` | Chooses Hugging Face or local GPU |
| `HF_TOKEN` | environment variable or `.hf_token` | none | Hugging Face token for free mode |
| `CUDA_TAG` | top of `run_gpu.bat` | `cu121` | PyTorch CUDA build. Use `cu128` for RTX 50-series |
| Port | end of both `.bat` files | `8000` | Change `--port 8000` and the two URLs if the port is busy |

## Manual setup

Use this if you do not want to use the launchers.

Free mode:
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
$env:MODE="hf"
$env:HF_TOKEN="hf_your_token"     # optional
uvicorn main:app
```

GPU mode (Python 3.10 or 3.11, Git, C++ Build Tools):
```powershell
python -m venv venv-gpu
venv-gpu\Scripts\activate
git clone https://github.com/VAST-AI-Research/TripoSR.git
pip install --upgrade pip setuptools wheel
pip install cmake ninja pybind11 "numpy<2"
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements-gpu.txt
findstr /v /i /c:"torchmcubes" /c:"gradio" TripoSR\requirements.txt > TripoSR\requirements_img23d.txt
pip install -r TripoSR\requirements_img23d.txt
pip install --no-build-isolation git+https://github.com/tatsy/torchmcubes.git
$env:MODE="local"
uvicorn main:app
```

Then open http://127.0.0.1:8000.

## Tips for good results

- Use one object on a plain background.
- Keep the object fully in frame and well lit.
- Avoid glass, mirrors, and very thin parts.
- A single photo gives a guessed 3D shape. The back and hidden sides are generated by the model, so the result is not suitable for exact measurements.
- STL files have no color or texture. They suit 3D printing, not display.

## Troubleshooting

**"The free GPU quota is used up"**
Wait for the time shown in the message, or add a Hugging Face token (see above). Compare mode uses the quota twice.

**"The free GPU service failed on this image or is busy"**
Try again, use the Auto engine, or use a simpler image with a plain background.

**"The online model changed its interface"**
The Hugging Face Space was updated. Try the other engine. To fix it, run the command below and compare the result with the calls in `engines.py`:
```powershell
python -c "from gradio_client import Client; Client('stabilityai/TripoSR').view_api()"
```

**Python not found**
Install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH". GPU mode needs 3.10 or 3.11.

**`torchmcubes` fails to compile (GPU mode)**
- Make sure the "Desktop development with C++" workload of the Visual Studio Build Tools is installed, then run `run_gpu.bat` again.
- If the error mentions CUDA, uninstall the CUDA Toolkit or remove it from PATH, then run again. `torchmcubes` then builds a CPU version, which is slightly slower but works.

**"PyTorch cannot use your GPU"**
Update your NVIDIA driver, delete the `venv-gpu` folder, and run `run_gpu.bat` again. For RTX 50-series cards set `CUDA_TAG` to `cu128` at the top of the file first.

**Out of GPU memory**
Close other programs that use the GPU, and set **Mesh detail** to Low.

**Port 8000 is already in use**
Change `8000` to another number in the `uvicorn` line and in the two `http://127.0.0.1:8000` URLs inside the launcher.

**Clear all history**
Stop the server, delete the `data` and `outputs` folders, and start it again.

**Start over from scratch**
Delete `venv`, `venv-gpu`, `TripoSR`, `data`, and `outputs`, then run the launcher again.

## Publish updates to GitHub

```powershell
git add .
git commit -m "Describe your change"
git push
```

## Credits

- [TripoSR](https://github.com/VAST-AI-Research/TripoSR) by Stability AI and Tripo AI (MIT license)
- [Stable Fast 3D](https://huggingface.co/stabilityai/stable-fast-3d) by Stability AI, used through a Hugging Face Space
- [`<model-viewer>`](https://modelviewer.dev/) by Google
- [FastAPI](https://fastapi.tiangolo.com/) and [trimesh](https://trimesh.org/)

Check each model's license before using results commercially.

---

Khaled 2026
