#!/usr/bin/env bash
set -e
cd "$(dirname "$(readlink -f "$0")")"

# ===== Settings (edit if needed) =====
# PyTorch CUDA build. cu121 works for most cards. RTX 50-series needs cu128.
CUDA_TAG="${CUDA_TAG:-cu121}"
VENV="venv-gpu"
# =====================================

echo "=================================================="
echo " img23d - GPU mode (runs on your NVIDIA GPU)"
echo "=================================================="

# 0. Project files
for f in main.py engines.py store.py photogrammetry.py capture.py certs.py serve.py local_triposr.py requirements-gpu.txt static/index.html; do
  [ -f "$f" ] || { echo "[ERROR] Missing $f"; exit 1; }
done
mkdir -p outputs

# 1. NVIDIA driver
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "[ERROR] nvidia-smi not found. Install the driver: sudo ubuntu-drivers autoinstall && reboot"
  echo "No NVIDIA GPU? Use ./run_free.sh instead."
  exit 1
fi
nvidia-smi -L

if [ ! -f "$VENV/.deps_ok" ]; then
  echo "First run: setting everything up. This can take 15-30 minutes."

  # 2. System packages
  sudo apt-get update
  sudo apt-get install -y git build-essential curl software-properties-common

  # 3. Python 3.10 or 3.11
  PYEXE=""
  for p in python3.11 python3.10 python3; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,11) else 1)'; then
      PYEXE="$p"; break
    fi
  done
  if [ -z "$PYEXE" ]; then
    echo "Installing Python 3.11 (deadsnakes)..."
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
    PYEXE=python3.11
  fi
  PYV="$("$PYEXE" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  sudo apt-get install -y "python${PYV}-venv" "python${PYV}-dev" 2>/dev/null || sudo apt-get install -y python3-venv python3-dev
  echo "Using Python: $PYEXE"

  # 4. TripoSR source
  if [ ! -f TripoSR/tsr/system.py ]; then
    rm -rf TripoSR
    git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git TripoSR
  fi

  # 5. Virtual environment
  [ -f "$VENV/bin/activate" ] || "$PYEXE" -m venv "$VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"

  # 6. Packages
  python -m pip install --upgrade pip setuptools wheel
  pip install cmake ninja pybind11 "numpy<2"
  pip install torch torchvision --index-url "https://download.pytorch.org/whl/${CUDA_TAG}"
  pip install -r requirements-gpu.txt
  grep -v -i -e torchmcubes -e gradio TripoSR/requirements.txt > TripoSR/requirements_img23d.txt
  pip install -r TripoSR/requirements_img23d.txt
  pip install scikit-build-core

  # torchmcubes: GPU build if the CUDA Toolkit (nvcc) exists, otherwise a CPU build
  # compiled against CPU-only torch (works fine with the CUDA torch at runtime).
  if command -v nvcc >/dev/null 2>&1 && pip install --no-build-isolation git+https://github.com/tatsy/torchmcubes.git; then
    echo "torchmcubes built with CUDA."
  else
    TORCH_VER="$(python -c 'import torch; print(torch.__version__.split("+")[0])')"
    rm -rf /tmp/img23d_cpuvenv /tmp/img23d_tmwheel
    "$PYEXE" -m venv /tmp/img23d_cpuvenv
    /tmp/img23d_cpuvenv/bin/pip install --upgrade pip
    /tmp/img23d_cpuvenv/bin/pip install "torch==${TORCH_VER}" --index-url https://download.pytorch.org/whl/cpu
    /tmp/img23d_cpuvenv/bin/pip install scikit-build-core cmake ninja pybind11 "numpy<2"
    ( source /tmp/img23d_cpuvenv/bin/activate && \
      pip wheel --no-build-isolation --no-deps git+https://github.com/tatsy/torchmcubes.git -w /tmp/img23d_tmwheel )
    pip install --no-deps /tmp/img23d_tmwheel/torchmcubes*.whl
    rm -rf /tmp/img23d_cpuvenv
  fi

  # keep numpy 1.x and a matching OpenCV
  pip install "numpy<2" "opencv-python-headless<4.11"

  echo ok > "$VENV/.deps_ok"
  echo "Setup complete."
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
if ! python -c 'import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; then
  echo "[ERROR] PyTorch cannot use your GPU."
  echo "Fix: update NVIDIA driver, delete the folder $VENV, run again."
  echo "RTX 50-series: CUDA_TAG=cu128 ./run_gpu.sh"
  exit 1
fi

# many-photo and live-capture packages (optional, does not stop the app)
if [ ! -f "$VENV/.deps_mv2_ok" ]; then
  echo "Installing many-photo and live-capture packages. This can take a few minutes..."
  if pip install -r requirements-multiview.txt "numpy<2" "opencv-python-headless<4.11"; then
    echo ok > "$VENV/.deps_mv2_ok"
  else
    echo "[WARNING] The many-photo packages could not be installed. One-photo mode still works."
  fi
fi

export MODE=local
echo
echo "Starting img23d at http://127.0.0.1:8000  (Ctrl+C to stop)"
echo "The first start downloads the model weights. This can take a few minutes."
(
  for _ in $(seq 1 900); do
    if curl -fsS -m 2 http://127.0.0.1:8000/config >/dev/null 2>&1; then
      command -v xdg-open >/dev/null 2>&1 && xdg-open http://127.0.0.1:8000 >/dev/null 2>&1
      break
    fi
    sleep 2
  done
) &
exec python serve.py
