# img23d

Turn a single photo into a 3D model in your browser. Upload an image, wait a minute, rotate the result, and download it as a `.glb` file.

Built with FastAPI, a plain HTML frontend, and [`<model-viewer>`](https://modelviewer.dev/) for the 3D preview.

## Two ways to run it

| | Free mode | GPU mode |
|---|---|---|
| Launcher | `run_free.bat` | `run_gpu.bat` |
| Needs a GPU in your PC | No | Yes, NVIDIA with about 6 GB VRAM or more |
| Where the model runs | Free Hugging Face Space (Stable Fast 3D) | Your own GPU (TripoSR) |
| Internet needed while using it | Yes | Only for the first setup |
| Speed | 30-90 seconds, slower when the Space is busy | A few seconds |
| Privacy | Images are sent to a public Hugging Face Space | Images never leave your PC |
| First-run setup | A few minutes | 15-30 minutes |

## Quick start (Windows)

1. Download or clone this project and keep all files together in one folder.
2. Double-click the launcher you want:
   - **No GPU:** `run_free.bat`
   - **NVIDIA GPU:** `run_gpu.bat`
3. Your browser opens at `http://127.0.0.1:8000`. Upload an image and click **Build 3D model**.
4. Close the black terminal window to stop the server.

Each launcher does the setup for you on the first run. Later runs start straight away.

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

The first start also downloads the TripoSR model weights, so it takes a few minutes. After that it starts quickly.

## Hugging Face token (free mode)

The free Hugging Face Space gives anonymous users a small GPU quota. A free token raises it and avoids most "upstream error" failures.

1. Make a free account at https://huggingface.co
2. Open https://huggingface.co/settings/tokens and create a token of type **Read**.
3. Paste it when `run_free.bat` asks. It is saved in `.hf_token` next to the launcher. This file is ignored by Git and is never uploaded.

To change the token, delete `.hf_token` and run the launcher again.

## Project structure

```
img23d/
  main.py               FastAPI server and API
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

Created on first run and ignored by Git: `venv/`, `venv-gpu/`, `outputs/`, `TripoSR/`, `.hf_token`.

## Configuration

| Setting | Where | Default | Purpose |
|---|---|---|---|
| `MODE` | set by the launchers | `hf` / `local` | Chooses Hugging Face or local GPU |
| `HF_TOKEN` | environment variable or `.hf_token` | none | Hugging Face token for free mode |
| `CUDA_TAG` | top of `run_gpu.bat` | `cu121` | PyTorch CUDA build. Use `cu128` for RTX 50-series |
| `mc_resolution` | `local_triposr.py` | `256` | Mesh detail. Lower it if you run out of GPU memory |
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

## Troubleshooting

**"The upstream Gradio app has raised an exception" (free mode)**
The Hugging Face Space is busy or your anonymous quota is used up. Add a Hugging Face token (see above), wait a few minutes, and try again. Test with a simple image under 2 MB.

**Python not found**
Install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH". GPU mode needs 3.10 or 3.11.

**`torchmcubes` fails to compile (GPU mode)**
- Make sure the "Desktop development with C++" workload of the Visual Studio Build Tools is installed, then run `run_gpu.bat` again.
- If the error mentions CUDA, uninstall the CUDA Toolkit or remove it from PATH, then run again. `torchmcubes` then builds a CPU version, which is slightly slower but works.

**"PyTorch cannot use your GPU"**
Update your NVIDIA driver, delete the `venv-gpu` folder, and run `run_gpu.bat` again. For RTX 50-series cards set `CUDA_TAG` to `cu128` at the top of the file first.

**Out of GPU memory**
Close other programs that use the GPU, or lower `mc_resolution` in `local_triposr.py`.

**Port 8000 is already in use**
Change `8000` to another number in the `uvicorn` line and in the two `http://127.0.0.1:8000` URLs inside the launcher.

**Start over from scratch**
Delete `venv`, `venv-gpu`, and `TripoSR`, then run the launcher again.

## Publish on GitHub

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/img23d.git
git push -u origin main
```

Create the empty repository on github.com first. Add a `LICENSE` file of your choice before sharing.

## Credits

- [TripoSR](https://github.com/VAST-AI-Research/TripoSR) by Stability AI and Tripo AI (MIT license)
- [Stable Fast 3D](https://huggingface.co/stabilityai/stable-fast-3d) by Stability AI, used through a Hugging Face Space
- [`<model-viewer>`](https://modelviewer.dev/) by Google
- [FastAPI](https://fastapi.tiangolo.com/)

Check each model's license before using results commercially.

---

Khaled 2026
