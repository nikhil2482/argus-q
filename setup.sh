#!/usr/bin/env bash
# One-step setup for macOS or Linux:   bash setup.sh
# Creates a Python environment, installs dependencies, runs the tests and the
# offline demo. The environment lives in ~/.venvs/argus-q, outside this folder,
# so cloud sync (iCloud Documents) never has to upload thousands of package files.
set -euo pipefail
cd "$(dirname "$0")"
VENV="${ARGUS_VENV:-$HOME/.venvs/argus-q}"
REPO="https://github.com/nikhil2482/argus-q.git"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# 1. A Python of 3.10 or newer
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  say "Python 3.10 or newer is required."
  echo "Install it with Homebrew (brew install python@3.12) or from https://www.python.org/downloads/ and run this again."
  exit 1
fi
say "Using $($PY --version) at $(command -v $PY)"

# 2. Disk space check (the packages need roughly 1 GB)
FREE_KB=$(df -Pk "$HOME" | awk 'NR==2 {print $4}')
if [ "${FREE_KB:-0}" -lt 2000000 ]; then
  say "Warning: less than 2 GB free on this disk. Installation may fail."
fi

# 3. Connect this folder to GitHub if it is not a git checkout yet
if [ ! -d .git ] && command -v git >/dev/null 2>&1; then
  say "Linking this folder to $REPO"
  git init -q -b main
  git remote add origin "$REPO"
  if git fetch -q origin main 2>/dev/null; then
    git reset -q origin/main
    git branch -q --set-upstream-to=origin/main main
    echo "Linked. 'git pull' will now get updates."
  else
    echo "Could not reach GitHub (sign in with 'gh auth login' or a token). The code still works without it."
  fi
fi

# 4. Environment and packages
if [ ! -x "$VENV/bin/python" ]; then
  say "Creating Python environment at $VENV"
  mkdir -p "$(dirname "$VENV")"
  "$PY" -m venv "$VENV"
fi
say "Installing packages (a few minutes the first time)"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r requirements.txt

# 5. Settings file
if [ ! -f .env ]; then
  cp .env.example .env
  say "Created .env. Open it and paste your ANTHROPIC_API_KEY and OPENALEX_EMAIL."
fi
mkdir -p runs

# 6. Check it works
say "Running tests"
"$VENV/bin/python" -m pytest -q tests
say "Running the offline demo"
"$VENV/bin/python" run.py demo | tail -3

say "Setup complete."
cat <<EOF

To use ARGUS-Q, open Terminal and run:

  cd "$(pwd)"
  source "$VENV/bin/activate"
  streamlit run app.py                  # dashboard
  python run.py eval --trials 3         # needs ANTHROPIC_API_KEY in .env
  python run.py investigate --mode live

EOF
