#!/usr/bin/env bash
set -e
cd "$(dirname "$(readlink -f "$0")")"

echo "=================================================="
echo " img23d - Free mode (uses a free Hugging Face GPU)"
echo "=================================================="

# 1. Python 3.10+
PYEXE=""
for p in python3.12 python3.11 python3.10 python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)'; then
    PYEXE="$p"; break
  fi
done
if [ -z "$PYEXE" ]; then
  echo "Installing Python..."
  sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
  PYEXE=python3
fi
if ! "$PYEXE" -c 'import venv, ensurepip' >/dev/null 2>&1; then
  sudo apt-get update && sudo apt-get install -y python3-venv python3-pip
fi

# 2. Project files
for f in main.py engines.py store.py photogrammetry.py capture.py certs.py serve.py requirements.txt static/index.html; do
  [ -f "$f" ] || { echo "[ERROR] Missing $f"; exit 1; }
done
mkdir -p outputs

# 3. Virtual environment
[ -f venv/bin/activate ] || "$PYEXE" -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

# 4. Packages
if [ ! -f venv/.deps_free_v2_ok ]; then
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  echo ok > venv/.deps_free_v2_ok
fi

# 4b. Many-photo packages (optional, does not stop the app)
if [ ! -f venv/.deps_mv2_ok ]; then
  echo "Installing many-photo and live-capture packages. This can take a few minutes..."
  if pip install -r requirements-multiview.txt; then
    echo ok > venv/.deps_mv2_ok
  else
    echo "[WARNING] The many-photo packages could not be installed. One-photo mode still works."
    echo "Python 3.11 or 3.12 gives the best chance. See Troubleshooting in README.md."
  fi
fi

# 5. Hugging Face token (optional)
if [ -z "${HF_TOKEN:-}" ] && [ -f .hf_token ]; then HF_TOKEN="$(cat .hf_token)"; fi
if [ -z "${HF_TOKEN:-}" ]; then
  echo
  echo "Create a free token at https://huggingface.co/settings/tokens (type: Read)"
  read -r -p "Paste your token here, or press Enter to skip: " HF_TOKEN || true
  [ -n "${HF_TOKEN:-}" ] && echo "$HF_TOKEN" > .hf_token
fi
export HF_TOKEN

# 6. Start
export MODE=hf
echo
echo "Starting img23d at http://127.0.0.1:8000  (Ctrl+C to stop)"
(
  for _ in $(seq 1 300); do
    if curl -fsS -m 2 http://127.0.0.1:8000/config >/dev/null 2>&1; then
      command -v xdg-open >/dev/null 2>&1 && xdg-open http://127.0.0.1:8000 >/dev/null 2>&1
      break
    fi
    sleep 2
  done
) &
exec python serve.py
