Turn photos into a 3D model in your browser. Upload one photo for a fast model, or many photos of the same object for a more complete and more accurate one. Rotate the result and download it as GLB, STL, or OBJ.

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
- **Many photos mode:** upload 4 to 80 photos taken around one object. The app finds where each photo was taken, cuts the object out, and builds a measured shape with real colors. It runs on the CPU, so no GPU is needed.
- **GPU mode:** run TripoSR on your own NVIDIA GPU with no online service.

## Many photos (more accurate)

One photo gives a guessed shape: the back and hidden sides are invented by the model. Many photos give a shape that is measured from your own pictures.

**How it works**
1. Structure from Motion (`pycolmap`) works out where every photo was taken.
2. The object is cut out of each photo (`rembg`, with a GrabCut fallback).
3. The cut-outs are combined with the camera positions into a smooth 3D shape (an implicit visual hull) using marching cubes.
4. Colors are painted from the photos that face each part of the surface best.
5. The model is stood upright, centred, and scaled to a size of 1.

**How to take the photos**
- Put the object on a plain surface and walk around it. Do not spin the object, because the background must stay still.
- Take 20 to 60 photos in a full circle. Each photo should overlap the last by about two thirds.
- Make a second circle higher up, and a third lower down if you can.
- Keep the whole object in every photo, filling about half of the frame.
- Use steady, even light. No flash and no moving shadows.
- Avoid shiny, see-through, and very dark objects.
- A textured background (a printed cloth, a wooden table, a newspaper) helps the camera positions work out.

**What to expect**
- 4 photos is the minimum and 80 is the maximum. 20 to 60 works best.
- It takes about 2 to 10 minutes on a normal PC, depending on the number of photos and the Detail option.
- The shape follows the outline of the object in every photo. It captures bumps and overall form well, but cannot see into hollow spaces such as the inside of a cup.
- The size is relative, not in centimetres. The model is scaled to a size of 1.
- The first run downloads the background-removal model (about 170 MB).

**Options:** Detail (Draft, Standard, Fine) sets the resolution of the shape, and "Paint colors from the photos" turns vertex colors on or off.

## Live phone capture (guided)

Use your phone as a guided camera. It shows which sides of the object are still needed (red) and which are done (green), takes the photos for you while you walk around, and sends them straight to your computer. When the whole object is covered, press **Build** on the computer. It uses the many-photos pipeline above.

**Set up**
1. Put the phone and the computer on the same Wi-Fi, or connect the computer to the phone's hotspot.
2. Start the app with a launcher, open the **Live phone** tab, and click **Connect my phone**.
3. Scan the QR code with the phone camera, or type the address shown into the phone browser.
4. The phone shows a security warning because the certificate is made on your own computer. Tap **Advanced**, then **Proceed** (or **Visit this website**). You only need to do this once per computer address.
5. Tap **Start camera** and allow the camera and motion access.
6. Stand where you want to begin, point the camera at the middle of the object, hold still, and tap **Start here**.

**While capturing**
- The round map shows 54 areas: 18 directions around the object and 3 heights. You start at the bottom of the circle. Walk to the left around the object. The outer ring is photos from a low angle, the middle ring from a medium angle, and the inner ring from high up looking down.
- Red means the area still needs a photo. Green with a check mark means it is done. The screen edge glows the same color, and a text hint tells you which way to step.
- A photo is taken automatically when the phone is held steady, the image is sharp, and the area is still red. Tap the round button to take one yourself.
- Keep the object in the middle of the screen the whole time. Walk around it in a circle, do a second circle holding the phone higher, and a third lower if you can.
- Tap **Finish** on the phone when you are done. The computer shows the same map and every photo. Delete a bad photo with the **x** on its thumbnail.

**What it uses**
- The phone's motion sensors work out which side of the object the phone is on. They are relative to the spot where you tapped **Start here**, so the compass is not used and metal in the room does not matter.
- Sensor tracking drifts a little over a few minutes. The map is a guide. The real camera positions are worked out from the photos afterwards.
- Only the phone page is reachable from your network. It is protected by a secret link that exists only while the session is open. The rest of the app stays on `127.0.0.1`.

## Two ways to run it

| | Free mode | GPU mode |
|---|---|---|
| Launcher | `run_free.bat` or `run_free.sh` | `run_gpu.bat` or `run_gpu.sh` |
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

## Quick start (Ubuntu / Linux)

```bash
chmod +x run_free.sh run_gpu.sh
./run_free.sh     # no GPU
./run_gpu.sh      # NVIDIA GPU (RTX 50-series: CUDA_TAG=cu128 ./run_gpu.sh)
```

Then open http://127.0.0.1:8000.

Notes for Linux:
- `run_gpu.sh` installs the needed apt packages (git, build-essential) and Python 3.11 if missing, so it asks for `sudo`.
- Without the CUDA Toolkit, `torchmcubes` is built as a CPU version automatically. This is slightly slower but works.
- To keep the terminal log: `bash run_gpu.sh 2>&1 | tee log.txt`

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

The steps below describe the Windows `.bat` files. The Ubuntu `.sh` files do the same job with `apt` instead of `winget`.

### `run_free.bat`
1. Checks that Python 3.10 or newer is installed.
2. Checks that the project files exist and creates the `outputs` folder.
3. Creates a virtual environment in `venv`.
4. Installs the packages from `requirements.txt`.
5. Installs the many-photo packages from `requirements-multiview.txt`. If this fails, one-photo mode still works.
6. Asks for an optional Hugging Face token and saves it to `.hf_token` (see below).
7. Starts the server and opens your browser when it is ready.

### `run_gpu.bat`
1. Checks that an NVIDIA driver is installed (`nvidia-smi`).
2. Finds Python 3.10 or 3.11, or offers to install Python 3.11 with `winget`.
3. Checks for Git, or offers to install it with `winget`.
4. Downloads the TripoSR source code into the `TripoSR` folder.
5. Checks for the Visual Studio C++ Build Tools, or offers to install them with `winget`.
6. Checks for the CUDA Toolkit, or offers to install it with `winget` (optional).
7. Creates a separate virtual environment in `venv-gpu`.
8. Installs PyTorch with CUDA, the app packages from `requirements-gpu.txt`, the TripoSR packages, and compiles `torchmcubes`.
9. Installs the many-photo packages from `requirements-multiview.txt`. If this fails, one-photo mode still works.
10. Verifies that PyTorch can see your GPU, then starts the server and opens your browser when it is ready.

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
  serve.py              Starts the app on this PC and the phone capture page
  capture.py            Live capture sessions and the phone-facing routes
  certs.py              Makes the HTTPS certificate for the phone page
  store.py              SQLite job history
  photogrammetry.py     Many-photo reconstruction: camera positions, carving, mesh, colors
  local_triposr.py      TripoSR inference code (GPU mode)
  static/
    index.html          Web interface
    capture.html        Phone capture page
    dome.js             Coverage map and sensor math, used by both pages
  requirements.txt      Packages for free mode
  requirements-gpu.txt  Packages for GPU mode
  requirements-multiview.txt  Packages for many-photo mode
  run_free.bat          Launcher: no GPU (Windows)
  run_gpu.bat           Launcher: NVIDIA GPU (Windows)
  run_free.sh           Launcher: no GPU (Ubuntu/Linux)
  run_gpu.sh            Launcher: NVIDIA GPU (Ubuntu/Linux)
  README.md
  .gitignore
  .gitattributes        Keeps .sh files on LF and .bat files on CRLF
```

Created on first run and ignored by Git: `venv/`, `venv-gpu/`, `outputs/` (images and models), `data/` (history database), `TripoSR/`, `.hf_token`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/config` | Mode, available engines, token status, and whether many-photo mode is ready |
| POST | `/api/jobs` | Upload an image and queue a job. Form fields: `file`, `engine`, `foreground_ratio`, `mesh_detail`, `remesh`, `texture_size` |
| POST | `/api/capture` | Start a live capture session. Returns the phone address and a QR code |
| GET | `/api/capture/{id}` | Photos received and coverage map for a session |
| DELETE | `/api/capture/{id}/photos/{n}` | Delete one photo from a session |
| POST | `/api/capture/{id}/build` | Build a model from the session photos. Form fields: `quality`, `colors` |
| DELETE | `/api/capture/{id}` | Cancel a session and delete its photos |
| POST | `/api/jobs/multi` | Upload 4 to 80 photos of one object and queue a job. Form fields: `files` (repeat for each photo), `quality` (`draft`, `standard`, `fine`), `colors` (`true` or `false`) |
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
| `PORT` | environment variable | `8000` | Port for the app on this computer |
| `HTTPS_PORT` | environment variable | `8443` | Port for the phone capture page |
| `CAPTURE_HOST` | environment variable | detected | The address your phone should use, if the detected one is wrong (for example when a VPN is active) |

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
- For the best accuracy, use Many photos mode.

## Troubleshooting

**"Many-photo mode needs extra packages"**
The packages in `requirements-multiview.txt` did not install. Python 3.11 or 3.12 gives the best chance. Delete `venv\.deps_mv_ok` (or `venv/.deps_mv_ok`) if it exists, run the launcher again, and read the error it prints. You can also run `pip install -r requirements-multiview.txt` inside the virtual environment.

**"Could not work out the camera positions"**
The photos do not overlap enough, or the background has no texture or moves. Take more photos with about two thirds overlap, in steady light, and walk around the object instead of spinning it.

**"Only N of M photos could be placed in 3D"**
Some photos are blurry, too dark, or from angles the others do not cover. Retake those, or remove them.

**"The object could not be separated from the background"**
Use a background that contrasts with the object and keep the whole object in view. Cutting out the object needs the `rembg` model, which downloads on first use, so check your internet connection.

**The many-photo model has a blob or extra parts**
Extra shapes come from photos where the object was cut out badly or the camera positions drifted. Remove the worst photos, use a plain background, and add photos from higher and lower angles.

**Live capture says it is not available**
It needs the packages `cryptography` and `segno` from `requirements-multiview.txt`. Run the launcher again. If the message mentions a port, another program is using `HTTPS_PORT`; set a different one.

**The phone cannot open the address**
- Make sure the phone and the computer are on the same Wi-Fi. Guest networks often block devices from reaching each other. The phone's hotspot works well.
- When Windows asks to allow Python through the firewall, choose **Private networks**. To fix it later, open Windows Security, then Firewall & network protection, then Allow an app through firewall.
- If the address shown starts with an unexpected number (for example from a VPN), start the app with `CAPTURE_HOST` set to the computer's Wi-Fi address.

**The phone says the camera or motion sensors are not available**
Open the page over `https://` (the QR code does), accept the security warning, use Chrome or Safari, and allow the camera and motion access. On an iPhone, the motion permission prompt appears when you tap **Start camera**. If you refused it, close the tab, reopen the page, and allow it.

**The map does not follow my movement, or jumps around**
Hold the phone upright and point it at the middle of the object. Walk slowly in a circle. If the map drifts after a few minutes, tap **Finish**, then start a new session for the next round of photos.

**Many photos run slowly**
Use the Draft detail option first, use fewer photos (30 is plenty for most objects), and close other programs.

**"The free GPU quota is used up"**
Wait for the time shown in the message, or add a Hugging Face token (see above). Compare mode uses the quota twice.

**"The free GPU service failed on this image or is busy"**
Try again, use the Auto engine, or use a simpler image with a plain background.

**"The online model changed its interface"**
The Hugging Face Space was updated. Try the other engine. To fix it, run the command below and compare the result with the calls in `engines.py`:
```powershell
python -c "from gradio_client import Client; Client('stabilityai/TripoSR').view_api()"
```

**`Permission denied` when running `./run_free.sh` (Linux)**
Run `chmod +x run_free.sh run_gpu.sh` once.

**`bad interpreter` or `^M` error when running a `.sh` file (Linux)**
The file has Windows line endings. Fix it with `sed -i 's/\r$//' run_free.sh run_gpu.sh`.

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
