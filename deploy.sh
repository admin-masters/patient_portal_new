#!/usr/bin/env bash
set -e

PROJECT_DIR=/home/ubuntu/peds_edu_app
VENV_DIR=/home/ubuntu/venv
PYTHON=$VENV_DIR/bin/python
PIP=$VENV_DIR/bin/pip
SERVICE_NAME=peds_edu   # matches /etc/systemd/system/peds_edu.service

cd "$PROJECT_DIR"

echo "[deploy] Ensuring venv exists..."
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

echo "[deploy] Installing requirements..."
$PIP install --upgrade pip
$PIP install -r requirements.txt

echo "[deploy] Ensuring .env exists (create from .env.example if missing)..."
if [ ! -f "$PROJECT_DIR/.env" ] && [ -f "$PROJECT_DIR/.env.example" ]; then
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
fi

echo "[deploy] Loading environment (.env if present)..."
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_DIR/.env"
  set +a
fi

echo "[deploy] Ensuring static dir exists to avoid warnings..."
mkdir -p "$PROJECT_DIR/static"

echo "[deploy] Ensuring migrations packages exist (init files)..."
mkdir -p "$PROJECT_DIR/accounts/migrations" "$PROJECT_DIR/catalog/migrations" "$PROJECT_DIR/sharing/migrations"
touch "$PROJECT_DIR/accounts/migrations/__init__.py" \
      "$PROJECT_DIR/catalog/migrations/__init__.py" \
      "$PROJECT_DIR/sharing/migrations/__init__.py"

echo "[deploy] Generating migrations for project apps..."
$PYTHON manage.py makemigrations accounts --noinput
$PYTHON manage.py makemigrations catalog --noinput
$PYTHON manage.py makemigrations sharing --noinput

echo "[deploy] Running migrations..."
$PYTHON manage.py migrate --noinput --fake-initial

echo "[deploy] Collecting static files..."
$PYTHON manage.py collectstatic --noinput || true

echo "[deploy] Ensuring gunicorn exists..."
if [ ! -f "$VENV_DIR/bin/gunicorn" ]; then
  $PIP install gunicorn
fi

echo "[deploy] Ensuring systemd can run 'start' (ExecStart=start)..."
# Create a robust start script in /usr/local/bin/start and link it to /usr/bin/start
# so systemd can find it via PATH in most configurations.
sudo tee /usr/local/bin/start >/dev/null <<EOF
#!/usr/bin/env bash
set -e

cd "$PROJECT_DIR"

# Load env if service didn't
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

# Sensible defaults (override via env if needed)
: "\${GUNICORN_BIND:=127.0.0.1:8000}"
: "\${GUNICORN_WORKERS:=3}"
: "\${GUNICORN_TIMEOUT:=60}"

exec "$VENV_DIR/bin/gunicorn" peds_edu.wsgi:application \\
  --bind "\$GUNICORN_BIND" \\
  --workers "\$GUNICORN_WORKERS" \\
  --timeout "\$GUNICORN_TIMEOUT"
EOF
sudo chmod +x /usr/local/bin/start
sudo ln -sf /usr/local/bin/start /usr/bin/start

echo "[deploy] Making sure systemd EnvironmentFile exists (copy .env to the exact path it expects)..."
UNIT_PATH=$(sudo systemctl show -p FragmentPath --value "$SERVICE_NAME" 2>/dev/null || true)
if [ -n "$UNIT_PATH" ] && [ -f "$UNIT_PATH" ] && [ -f "$PROJECT_DIR/.env" ]; then
  # Extract EnvironmentFile lines; supports optional leading '-' in EnvironmentFile=-/path/to/file
  while IFS= read -r line; do
    envpath="${line#EnvironmentFile=}"
    envpath="${envpath#-}"
    if [ -n "$envpath" ]; then
      sudo mkdir -p "$(dirname "$envpath")" || true
      sudo cp -f "$PROJECT_DIR/.env" "$envpath" || true
    fi
  done < <(sudo grep -E '^[[:space:]]*EnvironmentFile=' "$UNIT_PATH" || true)
fi

echo "[deploy] Reloading systemd units (safe)..."
sudo systemctl daemon-reload || true

echo "[deploy] Restarting gunicorn service..."
set +e
sudo systemctl restart "$SERVICE_NAME"
rc=$?
set -e

if [ $rc -ne 0 ]; then
  echo "[deploy] ERROR: service restart failed. Dumping status + logs + unit file..."
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
  sudo journalctl -u "$SERVICE_NAME" -n 200 --no-pager || true
  if [ -n "$UNIT_PATH" ] && [ -f "$UNIT_PATH" ]; then
    echo "----- [deploy] systemd unit ($UNIT_PATH) -----"
    sudo sed -n '1,200p' "$UNIT_PATH" || true
    echo "----- [deploy] end unit -----"
  fi
  exit $rc
fi

echo "[deploy] Done."
