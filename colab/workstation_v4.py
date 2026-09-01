# ================================================================
# OPENCODE + GOOGLE COLAB + DRIVE + GITHUB + NVIDIA NIM
# WORKSTATION PERSISTENTE / REANUDABLE - VERSION 4 - SIN AUTH WEB
# ================================================================
# Repo: https://github.com/enrrutador/opencode-colab-workstation (privado)
# Uso: Ejecuta esta única celda en Google Colab. No necesitas nada más.
# ================================================================

# ================================================================
# 0. IMPORTS
# ================================================================
import os, sys, json, time, shutil, socket, signal, subprocess, threading
from pathlib import Path
from IPython.display import display, HTML

print("\n" + "="*72)
print("        OPENCODE COLAB WORKSTATION")
print("        PERSISTENTE / REANUDABLE")
print("="*72 + "\n")

# ================================================================
# 1. FUNCIONES GENERALES
# ================================================================
def run_cmd(command, check=False, capture=False, env=None):
    result = subprocess.run(command, shell=True, text=True, capture_output=capture, env=env)
    if check and result.returncode != 0:
        error = result.stderr if result.stderr else ""
        raise RuntimeError(f"\nCOMMAND FAILED:\n{command}\n{error}")
    return result

def now(): return time.strftime("%Y-%m-%d %H:%M:%S")
def timestamp(): return time.strftime("%Y%m%d_%H%M%S")
def is_mounted(path):
    result = run_cmd("mount", capture=True)
    if result.returncode != 0: return False
    target = str(path)
    return any(target in line for line in result.stdout.splitlines())
def has_files(path):
    path = Path(path)
    if not path.exists(): return False
    try: return any(path.iterdir())
    except Exception: return False
def sync_dir(source, destination, delete=False):
    source, destination = Path(source), Path(destination)
    if not source.exists(): return
    destination.mkdir(parents=True, exist_ok=True)
    delete_flag = "--delete" if delete else ""
    run_cmd(f"rsync -a {delete_flag} '{source}/' '{destination}/'", check=False)
def port_open(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try: return sock.connect_ex((host, port)) == 0
    except Exception: return False
    finally: sock.close()

# ================================================================
# 2. GOOGLE DRIVE
# ================================================================
print("="*72 + "\n1/12  GOOGLE DRIVE\n" + "="*72 + "\n")
from google.colab import drive
MOUNT_CANDIDATES = [Path("/content/drive"), Path("/content/gdrive"), Path("/content/google_drive"), Path("/content/drive_mount")]
MOUNT_POINT = None
for candidate in MOUNT_CANDIDATES:
    if is_mounted(candidate):
        MOUNT_POINT = candidate
        print("✓ Google Drive ya está montado:", candidate); break
if MOUNT_POINT is None:
    selected = None
    preferred = Path("/content/drive")
    if not preferred.exists():
        preferred.mkdir(parents=True, exist_ok=True); selected = preferred
    else:
        try: empty = not any(preferred.iterdir())
        except Exception: empty = True
        if empty: selected = preferred
    if selected is None:
        for candidate in MOUNT_CANDIDATES[1:]:
            if not candidate.exists():
                candidate.mkdir(parents=True, exist_ok=True); selected = candidate; break
            try:
                if not any(candidate.iterdir()): selected = candidate; break
            except Exception: pass
    if selected is None: raise RuntimeError("No se encontró un punto de montaje limpio para Google Drive.")
    MOUNT_POINT = selected
    print("Montando Google Drive en:", MOUNT_POINT)
    drive.mount(str(MOUNT_POINT), force_remount=False)
print()
if not MOUNT_POINT.exists(): raise RuntimeError("Google Drive no quedó disponible.")
MY_DRIVE = MOUNT_POINT / "MyDrive"
if not MY_DRIVE.exists(): raise RuntimeError("No se encontró MyDrive.")
print("✓ Google Drive disponible.\n")

# ================================================================
# 3. ESTRUCTURA PERSISTENTE
# ================================================================
print("="*72 + "\n2/12  ESTRUCTURA PERSISTENTE\n" + "="*72 + "\n")
DRIVE_ROOT = MY_DRIVE / "opencode_colab"
DRIVE_STATE = DRIVE_ROOT / "state"
DRIVE_OPENCODE = DRIVE_STATE / "opencode"
DRIVE_OPENCODE_CONFIG = DRIVE_STATE / "config"
DRIVE_WORKSPACE = DRIVE_ROOT / "workspace"
DRIVE_BACKUPS = DRIVE_ROOT / "backups"
DRIVE_LOGS = DRIVE_ROOT / "logs"
DRIVE_SECRETS = DRIVE_ROOT / "secrets"
DRIVE_RUNTIME = DRIVE_STATE / "runtime.json"
DRIVE_CREDENTIALS = DRIVE_SECRETS / "credentials.json"
for directory in [DRIVE_ROOT, DRIVE_STATE, DRIVE_OPENCODE, DRIVE_OPENCODE_CONFIG, DRIVE_WORKSPACE, DRIVE_BACKUPS, DRIVE_LOGS, DRIVE_SECRETS]:
    directory.mkdir(parents=True, exist_ok=True)
LOCAL_ROOT = Path("/content/opencode_runtime")
LOCAL_WORKSPACE = LOCAL_ROOT / "workspace"
LOCAL_LOGS = LOCAL_ROOT / "logs"
LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
LOCAL_WORKSPACE.mkdir(parents=True, exist_ok=True)
LOCAL_LOGS.mkdir(parents=True, exist_ok=True)
HOME = Path.home()
REAL_OPENCODE_DATA = HOME / ".local" / "share" / "opencode"
REAL_OPENCODE_CONFIG = HOME / ".config" / "opencode"
REAL_OPENCODE_DATA.mkdir(parents=True, exist_ok=True)
REAL_OPENCODE_CONFIG.mkdir(parents=True, exist_ok=True)
print("Drive:", DRIVE_ROOT, "\n")

# ================================================================
# 4. RESTAURAR ESTADO
# ================================================================
print("="*72 + "\n3/12  RESTAURANDO ESTADO\n" + "="*72 + "\n")
if has_files(DRIVE_OPENCODE):
    print("Restaurando historial de OpenCode..."); sync_dir(DRIVE_OPENCODE, REAL_OPENCODE_DATA, delete=True); print("✓ Historial restaurado.")
else: print("• No existe historial anterior.")
if has_files(DRIVE_OPENCODE_CONFIG):
    print("Restaurando configuración..."); sync_dir(DRIVE_OPENCODE_CONFIG, REAL_OPENCODE_CONFIG, delete=True); print("✓ Configuración restaurada.")
if has_files(DRIVE_WORKSPACE):
    print("Restaurando workspace..."); sync_dir(DRIVE_WORKSPACE, LOCAL_WORKSPACE, delete=True); print("✓ Workspace restaurado.")
else: print("• Workspace nuevo.")
print()

# ================================================================
# 5. DEPENDENCIAS
# ================================================================
print("="*72 + "\n4/12  DEPENDENCIAS\n" + "="*72 + "\n")
run_cmd("apt-get update -qq && apt-get install -y -qq git curl wget jq rsync unzip zip procps ca-certificates", check=True)
node_check = run_cmd("node --version", capture=True)
if node_check.returncode != 0:
    print("Node.js no encontrado. Instalando Node.js 22...")
    run_cmd("curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs", check=True)
NODE_VERSION = run_cmd("node --version", capture=True).stdout.strip()
NPM_VERSION = run_cmd("npm --version", capture=True).stdout.strip()
print("Node:", NODE_VERSION); print("NPM:", NPM_VERSION, "\n")

# ================================================================
# 6. OPENCODE
# ================================================================
print("="*72 + "\n5/12  OPENCODE\n" + "="*72 + "\n")
opencode_check = run_cmd("which opencode", capture=True)
if opencode_check.returncode != 0:
    print("OpenCode no está instalado. Instalando..."); run_cmd("npm install -g opencode-ai", check=True)
OPENCODE_BIN = shutil.which("opencode")
if not OPENCODE_BIN: raise RuntimeError("No se encontró OpenCode.")
OPENCODE_VERSION = run_cmd("opencode --version", capture=True).stdout.strip()
print("✓ OpenCode:", OPENCODE_VERSION); print("Binario:", OPENCODE_BIN, "\n")

# ================================================================
# 7. CREDENCIALES
# ================================================================
print("="*72 + "\n6/12  CREDENCIALES\n" + "="*72 + "\n")
credentials = {}
if DRIVE_CREDENTIALS.exists():
    try: credentials = json.loads(DRIVE_CREDENTIALS.read_text(encoding="utf-8")); print("✓ Credenciales persistentes encontradas.")
    except Exception: credentials = {}
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "") or credentials.get("nvidia_api_key", "")
if not NVIDIA_API_KEY:
    print("\nPrimera configuración NVIDIA NIM.\n"); NVIDIA_API_KEY = input("Pegá tu NVIDIA API Key: ").strip()
if not NVIDIA_API_KEY: raise RuntimeError("No se proporcionó NVIDIA API Key.")
os.environ["NVIDIA_API_KEY"] = NVIDIA_API_KEY
GITHUB_REPO = os.environ.get("GITHUB_REPO", "") or credentials.get("github_repo", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "") or credentials.get("github_token", "")
if not GITHUB_REPO:
    print("\nConfiguración de GitHub.\n"); GITHUB_REPO = input("URL HTTPS del repositorio GitHub: ").strip()
if GITHUB_REPO and not GITHUB_TOKEN: GITHUB_TOKEN = input("GitHub Personal Access Token: ").strip()
credentials["nvidia_api_key"] = NVIDIA_API_KEY
if GITHUB_REPO: credentials["github_repo"] = GITHUB_REPO
if GITHUB_TOKEN: credentials["github_token"] = GITHUB_TOKEN
DRIVE_CREDENTIALS.write_text(json.dumps(credentials, indent=2, ensure_ascii=False), encoding="utf-8")
try: os.chmod(DRIVE_CREDENTIALS, 0o600)
except Exception: pass
print("✓ Credenciales preparadas.\n")

# ================================================================
# 8. NVIDIA NIM
# ================================================================
print("="*72 + "\n7/12  NVIDIA NIM\n" + "="*72 + "\n")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
print("Consultando modelos NVIDIA...")
models_result = subprocess.run(["curl","-sS","--max-time","30","-H",f"Authorization: Bearer {NVIDIA_API_KEY}",f"{NVIDIA_BASE_URL}/models"], capture_output=True, text=True)
models_payload = {}
if models_result.returncode == 0:
    try: models_payload = json.loads(models_result.stdout)
    except Exception: pass
available_models = [item.get("id") for item in models_payload.get("data",[]) if item.get("id")]
print("Modelos encontrados:", len(available_models))
selected_model = credentials.get("nvidia_model", "")
if selected_model and selected_model not in available_models: selected_model = ""
if not selected_model:
    nemotron_models = [m for m in available_models if "nemotron" in m.lower()]
    if nemotron_models: selected_model = nemotron_models[0]
if not selected_model and available_models: selected_model = available_models[0]
if selected_model:
    credentials["nvidia_model"] = selected_model; print("Modelo seleccionado:", selected_model)
else: print("⚠ No se pudo seleccionar un modelo.")
DRIVE_CREDENTIALS.write_text(json.dumps(credentials, indent=2, ensure_ascii=False), encoding="utf-8")
print()

# ================================================================
# 9. CONFIGURACIÓN OPENCODE
# ================================================================
print("="*72 + "\n8/12  CONFIGURACIÓN OPENCODE\n" + "="*72 + "\n")
CONFIG_FILE = REAL_OPENCODE_CONFIG / "opencode.json"
new_config = {"$schema":"https://opencode.ai/config.json","permission":"allow","compaction":{"auto":True,"prune":False},"provider":{"nvidia":{"name":"NVIDIA NIM","npm":"@ai-sdk/openai-compatible","options":{"baseURL":NVIDIA_BASE_URL,"apiKey":"{env:NVIDIA_API_KEY}"},"models":{}}}}
if selected_model:
    new_config["provider"]["nvidia"]["models"][selected_model] = {"name": selected_model}
    new_config["model"] = "nvidia/" + selected_model
final_config = new_config
if CONFIG_FILE.exists():
    try:
        old_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(old_config, dict):
            final_config = dict(old_config)
            final_config["$schema"] = new_config["$schema"]
            final_config["permission"] = "allow"
            final_config["compaction"] = new_config["compaction"]
            final_config["provider"] = new_config["provider"]
            if selected_model: final_config["model"] = new_config["model"]
    except Exception: final_config = new_config
CONFIG_FILE.write_text(json.dumps(final_config, indent=2, ensure_ascii=False), encoding="utf-8")
print("Configuración escrita:", CONFIG_FILE, "\n")

# ================================================================
# 10. LIMPIAR AUTENTICACIÓN WEB ANTERIOR
# ================================================================
print("="*72 + "\n9/12  LIMPIANDO AUTENTICACIÓN WEB\n" + "="*72 + "\n")
for variable in ["OPENCODE_SERVER_PASSWORD","OPENCODE_SERVER_USERNAME","OPENCODE_SERVER_AUTH","OPENCODE_PASSWORD","OPENCODE_USERNAME"]:
    os.environ.pop(variable, None)
print("✓ Autenticación HTTP de OpenCode eliminada.\n✓ OpenCode Web funcionará sin usuario/contraseña.\n")

# ================================================================
# 11. GITHUB
# ================================================================
print("="*72 + "\n10/12  GITHUB\n" + "="*72 + "\n")
os.chdir(LOCAL_WORKSPACE)
if not (LOCAL_WORKSPACE / ".git").exists():
    run_cmd("git init", check=False); run_cmd("git checkout -B main", check=False)
run_cmd('git config user.name "OpenCode Colab"', check=False)
run_cmd('git config user.email "opencode-colab@localhost"', check=False)
if GITHUB_REPO:
    run_cmd("git remote remove origin", check=False)
    run_cmd(f"git remote add origin '{GITHUB_REPO}'", check=False)
if GITHUB_TOKEN:
    credential_file = LOCAL_ROOT / "git_credentials"
    credential_file.write_text(f"https://x-access-token:{GITHUB_TOKEN}@github.com\n", encoding="utf-8")
    try: os.chmod(credential_file, 0o600)
    except Exception: pass
    run_cmd(f"git config credential.helper 'store --file={credential_file}'", check=False)
gitignore = r"""
# Secrets
.env
.env.*
credentials.json
auth.json
git_credentials
# Runtime
*.pid
*.tmp
*.lock
# Logs
*.log
# Node
node_modules/
# Python
__pycache__/
*.pyc
# OS
.DS_Store
Thumbs.db
# Colab
/content/
"""
(LOCAL_WORKSPACE / ".gitignore").write_text(gitignore.strip()+"\n", encoding="utf-8")
if GITHUB_REPO:
    print("Consultando GitHub...")
    fetch = run_cmd("git fetch origin", capture=True)
    if fetch.returncode == 0:
        branches = run_cmd("git branch -r", capture=True)
        if "origin/main" in branches.stdout: run_cmd("git merge origin/main --no-edit", check=False)
run_cmd("git add -A", check=False)
status = run_cmd("git status --porcelain", capture=True)
if status.stdout.strip(): run_cmd('git commit -m "OpenCode Colab checkpoint"', check=False)
if GITHUB_REPO:
    push = run_cmd("git push -u origin main", capture=True)
    if push.returncode == 0: print("✓ GitHub sincronizado.")
    else:
        print("⚠ GitHub no pudo sincronizarse todavía.")
        if push.stderr: print(push.stderr[-2000:])
print()

# ================================================================
# 12. PERSISTENCIA
# ================================================================
print("="*72 + "\n11/12  PERSISTENCIA\n" + "="*72 + "\n")
sync_dir(REAL_OPENCODE_DATA, DRIVE_OPENCODE, delete=True)
sync_dir(REAL_OPENCODE_CONFIG, DRIVE_OPENCODE_CONFIG, delete=True)
sync_dir(LOCAL_WORKSPACE, DRIVE_WORKSPACE, delete=True)
runtime = {"runtime_started":now(),"opencode_version":OPENCODE_VERSION,"workspace":str(LOCAL_WORKSPACE),"persistent_workspace":str(DRIVE_WORKSPACE),"opencode_data":str(REAL_OPENCODE_DATA),"persistent_opencode_data":str(DRIVE_OPENCODE),"provider":"NVIDIA NIM","model":selected_model,"persistence":"Google Drive","github":GITHUB_REPO or "","web_authentication":False,"server_port":4096,"status":"initializing"}
DRIVE_RUNTIME.write_text(json.dumps(runtime, indent=2, ensure_ascii=False), encoding="utf-8")
print("✓ Estado persistido.\n")

# ================================================================
# 13. BACKUP
# ================================================================
def backup_all():
    try:
        sync_dir(REAL_OPENCODE_DATA, DRIVE_OPENCODE, delete=True)
        sync_dir(REAL_OPENCODE_CONFIG, DRIVE_OPENCODE_CONFIG, delete=True)
        sync_dir(LOCAL_WORKSPACE, DRIVE_WORKSPACE, delete=True)
        runtime_state = {"last_backup":now(),"opencode_version":OPENCODE_VERSION,"model":selected_model,"workspace":str(LOCAL_WORKSPACE),"persistent_workspace":str(DRIVE_WORKSPACE),"web_authentication":False,"server_port":4096}
        DRIVE_RUNTIME.write_text(json.dumps(runtime_state, indent=2, ensure_ascii=False), encoding="utf-8")
        if GITHUB_REPO:
            os.chdir(LOCAL_WORKSPACE)
            run_cmd("git add -A", check=False)
            status = run_cmd("git status --porcelain", capture=True)
            if status.stdout.strip():
                run_cmd('git commit -m "OpenCode automatic checkpoint"', check=False)
                run_cmd("git push origin main", check=False)
        return True
    except Exception as e: print("[BACKUP ERROR]", repr(e)); return False
print("[BACKUP] Guardando estado inicial..."); backup_all(); print("[BACKUP] ✓ completado.\n")

# ================================================================
# 14. INICIAR OPENCODE WEB
# ================================================================
print("="*72 + "\n12/12  INICIANDO OPENCODE WEB\n" + "="*72 + "\n")
SERVER_PORT = 4096
SERVER_LOG = LOCAL_LOGS / "opencode-web.log"
SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
server_env = os.environ.copy()
for variable in ["OPENCODE_SERVER_PASSWORD","OPENCODE_SERVER_USERNAME","OPENCODE_SERVER_AUTH","OPENCODE_PASSWORD","OPENCODE_USERNAME"]:
    server_env.pop(variable, None)
server_env["NVIDIA_API_KEY"] = NVIDIA_API_KEY
os.chdir(LOCAL_WORKSPACE)
SERVER_COMMAND = [OPENCODE_BIN, "web", "--hostname", "0.0.0.0", "--port", str(SERVER_PORT)]
print("Ejecutando:", " ".join(SERVER_COMMAND), "\n")
server_log_handle = open(SERVER_LOG, "a", encoding="utf-8")
OPENCODE_PROCESS = subprocess.Popen(SERVER_COMMAND, stdout=server_log_handle, stderr=server_log_handle, env=server_env, start_new_session=True)
print("PID:", OPENCODE_PROCESS.pid, "\n")

# ================================================================
# 15. ESPERAR SERVIDOR
# ================================================================
print("Esperando que OpenCode abra el puerto...")
SERVER_READY = False
for attempt in range(60):
    time.sleep(1)
    if OPENCODE_PROCESS.poll() is not None: break
    if port_open("127.0.0.1", SERVER_PORT): SERVER_READY = True; break
if not SERVER_READY:
    if OPENCODE_PROCESS.poll() is None:
        try: log_text = SERVER_LOG.read_text(encoding="utf-8")
        except Exception: log_text = ""
        if "Local access:" in log_text: SERVER_READY = True
if not SERVER_READY:
    print("\n❌ OpenCode no pudo iniciar.\nÚltimos logs:")
    try: print(SERVER_LOG.read_text(encoding="utf-8")[-12000:])
    except Exception: pass
    raise RuntimeError("OpenCode Web no pudo iniciar.")
print("\n✓ OpenCode Web está ejecutándose.\n✓ Puerto:", SERVER_PORT, "\n✓ Autenticación Web: DESACTIVADA\n")

# ================================================================
# 16. PROXY NATIVO COLAB
# ================================================================
print("Creando acceso mediante proxy de Google Colab...")
PROXY_URL = None
try:
    from google.colab import output
    PROXY_URL = output.eval_js("google.colab.kernel.proxyPort(4096)")
except Exception as e:
    print("⚠ No se pudo generar automáticamente el enlace del proxy.", repr(e))

# ================================================================
# 17. ESTADO FINAL
# ================================================================
runtime = {"runtime_started":now(),"server_started":now(),"pid":OPENCODE_PROCESS.pid,"server_ready":True,"port":SERVER_PORT,"proxy_url":PROXY_URL,"opencode_version":OPENCODE_VERSION,"model":selected_model,"workspace":str(LOCAL_WORKSPACE),"persistent_workspace":str(DRIVE_WORKSPACE),"provider":"NVIDIA NIM","persistence":"Google Drive","github":GITHUB_REPO or "","web_authentication":False,"status":"running"}
DRIVE_RUNTIME.write_text(json.dumps(runtime, indent=2, ensure_ascii=False), encoding="utf-8")

# ================================================================
# 18. WATCHDOG
# ================================================================
def watchdog():
    while True:
        try:
            time.sleep(180)
            if OPENCODE_PROCESS.poll() is not None:
                print("\n[WATCHDOG] OpenCode terminó.\n[WATCHDOG] Reiniciando...")
                new_log = open(SERVER_LOG, "a", encoding="utf-8")
                new_process = subprocess.Popen(SERVER_COMMAND, stdout=new_log, stderr=new_log, env=server_env, start_new_session=True)
                globals()["OPENCODE_PROCESS"] = new_process
                print("[WATCHDOG] Nuevo PID:", new_process.pid)
            print("[BACKUP]", now())
            if backup_all(): print("[BACKUP] ✓ completado.")
        except Exception as e: print("[WATCHDOG ERROR]", repr(e))
WATCHDOG_THREAD = threading.Thread(target=watchdog, daemon=True)
WATCHDOG_THREAD.start()

# ================================================================
# 19. BACKUP AL CERRAR
# ================================================================
def shutdown_backup(signum=None, frame=None):
    try: print("[SHUTDOWN] Guardando estado..."); backup_all()
    except Exception as e: print("[SHUTDOWN ERROR]", repr(e))
try: signal.signal(signal.SIGTERM, shutdown_backup)
except Exception: pass

# ================================================================
# 20. INTERFAZ
# ================================================================
print("\n" + "="*72 + "\n              🟢 OPENCODE LISTO\n" + "="*72 + "\n")
if PROXY_URL:
    display(HTML(f"""
            <div style="padding:30px;margin:20px 0;border-radius:16px;border:3px solid #22c55e;background:#111827;color:white;text-align:center;font-family:Arial,sans-serif;">
                <div style="font-size:30px;font-weight:bold;margin-bottom:15px;">🟢 OpenCode está funcionando</div>
                <div style="font-size:16px;margin-bottom:8px;">NVIDIA NIM ✓</div>
                <div style="font-size:16px;margin-bottom:8px;">Google Drive ✓</div>
                <div style="font-size:16px;margin-bottom:8px;">Historial persistente ✓</div>
                <div style="font-size:16px;margin-bottom:20px;">GitHub ✓</div>
                <a href="{PROXY_URL}" target="_blank" style="display:inline-block;padding:16px 34px;border-radius:10px;background:#22c55e;color:white;text-decoration:none;font-size:19px;font-weight:bold;">🚀 ABRIR OPENCODE</a>
            </div>
            """))
else: print("OpenCode está activo en: http://127.0.0.1:4096")

# ================================================================
# 21. INFORME FINAL
# ================================================================
print("\n" + "="*72 + "\nESTADO FINAL\n" + "="*72 + "\n")
print("OpenCode:", OPENCODE_VERSION); print("PID:", OPENCODE_PROCESS.pid); print("Puerto:", SERVER_PORT); print("Servidor: ACTIVO")
print("Autenticación Web: DESACTIVADA"); print("Drive: PERSISTENTE"); print("Historial: PERSISTENTE"); print("Workspace: PERSISTENTE")
print("NVIDIA NIM: ACTIVO"); print("Modelo:", selected_model or "no seleccionado")
print("GitHub:", "ACTIVO" if GITHUB_REPO else "NO CONFIGURADO"); print("Watchdog: ACTIVO"); print("Backup: ACTIVO")
print("\n" + "="*72 + "\n   NO EJECUTES NINGÚN COMANDO ADICIONAL\n" + "="*72 + "\n")
