# OpenCode Cloud Workstation

**Workstation de desarrollo persistente y reanudable para OpenCode sobre Kaggle.**

El runtime es reemplazable; la workstation no.

Un kernel Kaggle puede morir, reiniciarse o desaparecer. El trabajo del usuario **no** debe desaparecer con él.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version: v5](https://img.shields.io/badge/version-5.0.0-blue.svg)]()
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-yellow.svg)]()

> Arquitectura **Kaggle-only**. Sin Google Colab, sin Google Drive, sin `shell=True`, sin `bash -c` / `curl|bash`.  
> Runtime: **Kaggle Kernels** · Persistencia: **Kaggle Dataset** · Secretos: **Kaggle Secrets** · Código: **GitHub** (versionado, separado del checkpoint)

---

## Principio de diseño

```
Runtime Kaggle  =  efímero y reemplazable
Workstation     =  persistente y reanudable
```

La workstation vive en un **Kaggle Dataset**. Cada runtime nuevo:

1. descarga el Dataset con `kagglehub`
2. restaura estado local bajo `/kaggle/working/opencode_cloud/`
3. continúa el trabajo
4. publica de nuevo al Dataset según política de checkpoints

---

## Arquitectura

```
Teléfono / navegador
        │  HTTPS
        ▼
Kaggle Jupyter Proxy  (kkb-production…/proxy/proxy/<PORT>)
        │
        ▼
OpenCode Web  (local al runtime, default :4096)
        │
        ▼
Kaggle Runtime  (efímero)
        │
        ▼
OpenCode Workstation
        │
        ├── /kaggle/working/opencode_cloud/     ← store local temporal
        │        ├── workspace/
        │        ├── state/          (OpenCode data + config)
        │        ├── config/
        │        ├── checkpoints/
        │        ├── metadata/
        │        ├── logs/
        │        └── workstation.json   (marker de validez)
        │
        ├── Kaggle Dataset             ← persistencia de la workstation
        ├── GitHub                     ← versionado de código (opcional)
        ├── Kaggle Models              ← pesos / artefactos (cuando aplique)
        └── Kaggle Secrets             ← API keys (solo en memoria / env)
```

### Separación de responsabilidades

| Componente | Responsabilidad | Qué **no** hace |
|---|---|---|
| **PersistentStore** | Store local bajo `/kaggle/working/opencode_cloud/` | Publicar al Dataset |
| **KagglePersistence** | `kagglehub.dataset_download` / `dataset_upload` | Tratar `/kaggle/datasets` como FS escribible |
| **CheckpointManager** | Decidir *cuándo* publicar remoto | Ejecutar el upload |
| **Watchdog** | Reiniciar el proceso OpenCode si muere | Publicar Dataset ni `git push` |
| **GitHub** | Versionado de código | Ser la persistencia principal de la workstation |
| **Kaggle Secrets** | API keys en runtime | Escribir secretos a disco / Dataset / logs |

**Importante:** `/kaggle/datasets/...` **no** se usa como filesystem escribible.

```text
kagglehub.dataset_download(handle)  →  restore local
kagglehub.dataset_upload(handle, staging_dir)  ←  publish desde staging local
```

---

## Flujo de recovery (runtime nuevo)

Implementado en `opencode_kaggle.bootstrap.bootstrap()`:

1. Detectar Kaggle  
2. Crear `/kaggle/working/opencode_cloud/`  
3. Cargar secretos (`UserSecretsClient` / env)  
4. Resolver Dataset (`OPENCODE_CLOUD_DATASET` = `owner/dataset`)  
5. `kagglehub.dataset_download`  
6. Validar marker `workstation.json`  
7. Restaurar workspace / state / config a rutas de runtime  
8. Asegurar Node + OpenCode (**idempotente**)  
9. Configurar NVIDIA NIM (solo `{env:NVIDIA_API_KEY}`)  
10. Iniciar OpenCode Web (puerto local, default 4096)  
11. Resolver Kaggle Jupyter Proxy + HTTP probe  
12. Arrancar Watchdog (restart real + revalidate proxy) y CheckpointScheduler  
13. Checkpoint local; remoto según política  

### Estados de recovery

| Estado | Significado |
|---|---|
| `RESTORED_FROM_DATASET` | Restauración válida desde Dataset |
| `FRESH_WORKSTATION` | Dataset inexistente o vacío → workstation nueva |
| `RESTORE_FAILED` | Dataset presente pero inválido/corrupto (**no se finge éxito**) |

---

## Checkpoints (dos niveles)

### Nivel 1 — Local (barato, frecuente)

- Copia runtime → `/kaggle/working/opencode_cloud/`
- **No** crea versión de Dataset

### Nivel 2 — Remoto (caro, con política)

- Staging local → `kagglehub.dataset_upload`
- Política (`CheckpointManager`):

| Condición | Acción |
|---|---|
| Cambios significativos + ≥ **5 min** desde el último publish | Publicar |
| Shutdown ordenado (`SIGTERM` / `SIGINT`) | Publicar ya |
| Checkpoint explícito | Publicar ya |
| Solo cooldown sin cambios | No publicar |

`CheckpointManager` decide *si*.  
`KagglePersistence.publish_from_store()` ejecuta.

### Significant change detection

A workspace fingerprint (paths + sizes + mtimes) is compared before remote publish decisions.

| Situation | Publish? |
|---|---|
| No workspace changes | No (unless EXPLICIT / SHUTDOWN) |
| Significant change + ≥ 5 min since last publish | Yes (`COOLDOWN_AND_CHANGES`) |
| Explicit checkpoint | Yes (bypasses cooldown) |
| Ordered shutdown | Yes (bypasses cooldown) |

GitHub sync is **never** triggered by checkpoints. Use `github_sync.sync_to_remote` explicitly for code versioning.

---

## Watchdog

```text
OpenCode muerto → restart real (Popen nuevo) → revalidate proxy → registrar resultado
```

- Requiere `restart_fn` real (no `lambda: None`)
- Tras restart: revalida el proxy (estado efímero; no persiste URL/token)
- **No** publica Dataset
- **No** hace `git push`
- Muere con el runtime; la continuidad la da recovery + Dataset

---

## Secretos

```python
from kaggle_secrets import UserSecretsClient  # en Kaggle
```

| Clave | Uso |
|---|---|
| `NVIDIA_API_KEY` | **Requerido** — NVIDIA NIM |
| `OPENCODE_CLOUD_DATASET` | Config: `owner/dataset` (puede ser secreto o env) |
| `GITHUB_TOKEN` | Opcional — versionado |
| `GITHUB_REPO` | Opcional — URL HTTPS del repo |
| `OPENCODE_SERVER_PASSWORD` | Opcional — basic auth de OpenCode Web |

Los secretos **no** se escriben en Dataset, workspace, config de OpenCode, logs ni archivos de credenciales persistentes.

La config de OpenCode referencia la key solo como:

```json
"apiKey": "{env:NVIDIA_API_KEY}"
```

---

## GitHub (opcional)

Solo versionado de código. Credenciales **temporales**:

1. Archivo temporal **fuera** del workspace (`tempfile.mkstemp`)
2. `git config credential.helper store --file=...`
3. `git push` / `fetch`
4. **Borrar** el archivo en `finally` (también si git falla)

No hay `.git-credentials` persistente en el workspace ni token en el Dataset.

---

## OpenCode Web y acceso desde el teléfono

OpenCode Web escucha **localmente** en el runtime (default puerto `4096`, configurable vía `OPENCODE_PORT`).

El acceso externo usa el **Kaggle Jupyter Proxy**:

```text
https://kkb-production.jupyter-proxy.kaggle.net/k/<kernel>/<token>/proxy/proxy/<PORT>
```

La URL se construye con `jupyter_server.serverapp.list_running_servers()` → `base_url`.
**No se inventa.** Antes de marcar `available` / `proxy_http_ok`, el bootstrap hace un **HTTP GET** a esa URL pública.

| Concepto | Significado |
|---|---|
| `opencode_listening` | TCP local OK |
| `proxy_url_generated` | URL construida |
| `proxy_reachable` / `available` | Probe HTTP al proxy OK |
| `status=proxy_http_ok` | Solo conectividad HTTP — **no** prueba UI, WebSocket ni streaming |

La URL contiene un token de sesión Jupyter. **Permitido** mostrarla al usuario. **Prohibido** guardarla en Dataset, checkpoints, Git o logs persistentes (solo versión redactada en logs).

### Cómo usarlo

1. Ejecutá bootstrap en el notebook Kaggle.
2. Si `web_access.available` es true, copiá `web_access.url` y abrila en el teléfono.
3. Si el kernel se reinicia: restore del Dataset + **nueva URL** (la anterior no sirve).

### Lifecycle (runtime)

```text
START → OpenCode + Watchdog + CheckpointScheduler
  Watchdog: reinicia OpenCode y revalida proxy (no publica Dataset)
  Scheduler: checkpoints locales/remotos según política
SHUTDOWN (SIGINT/SIGTERM o info["shutdown"]())
  → stop watchdog → checkpoint final Dataset → stop scheduler → stop OpenCode
```

Shutdown es **idempotente**.

---

## Uso rápido (Kaggle)

### 1. Preparar

1. Crear un **Kaggle Dataset privado**, p. ej. `tu-usuario/opencode-workstation-persistence`
2. En **Settings → Secrets** del notebook:
   - `NVIDIA_API_KEY`
   - `OPENCODE_CLOUD_DATASET` = `tu-usuario/opencode-workstation-persistence`
   - (opcional) `GITHUB_TOKEN`, `GITHUB_REPO`, `OPENCODE_SERVER_PASSWORD`

### 2. Ejecutar

```python
!pip install -q kagglehub
!pip install -q git+https://github.com/enrrutador/opencode-colab-workstation.git@kaggle-migration

import opencode_kaggle.bootstrap as bs
info = bs.bootstrap()
print(info)
# Opcional al terminar la sesión:
# info["shutdown"]()
```

O abrir el notebook [`kaggle/Workstation.ipynb`](kaggle/Workstation.ipynb).

### 3. Resultado esperado

```python
{
  "ok": True,
  "runtime": "kaggle",
  "recovery": "FRESH_WORKSTATION",  # o RESTORED_FROM_DATASET
  "workspace": "/kaggle/working/opencode_cloud/workspace",
  "opencode_port": 4096,
  "opencode_pid": 12345,
  "model": "nvidia/...",
  "dataset_id": "tu-usuario/opencode-workstation-persistence",
  "web_access": {
    "available": true,
    "status": "proxy_http_ok",
    "proxy_reachable": true,
    "url": "https://kkb-production.jupyter-proxy.kaggle.net/k/.../proxy/proxy/4096",
    "url_redacted": "https://.../<REDACTED>/proxy/proxy/4096"
  },
  "shutdown": "<callable idempotente>"
}
```

---

## Estructura del repositorio

```text
opencode-colab-workstation/
├── src/
│   ├── opencode_cloud/          # núcleo
│   │   ├── access.py            # Kaggle Jupyter Proxy + HTTP probe
│   │   ├── ports.py             # OPENCODE_PORT centralizado
│   │   ├── runtime.py
│   │   ├── secrets.py
│   │   ├── nvidia.py
│   │   ├── opencode.py
│   │   ├── persistence.py
│   │   ├── checkpoint.py
│   │   ├── scheduler.py         # checkpoints automáticos
│   │   ├── watchdog.py          # restart OpenCode + revalidate proxy
│   │   └── github_sync.py
│   └── opencode_kaggle/
│       ├── bootstrap.py         # entry + shutdown idempotente
│       ├── kaggle.py
│       └── runtime.py
├── tests/
├── kaggle/Workstation.ipynb
├── scripts/install.sh
└── pyproject.toml
```

Ambos `opencode_cloud` y `opencode_kaggle` son paquetes instalables.  
En producción **no** se usa `sys.path.insert`.

---

## Desarrollo y tests

```bash
git clone https://github.com/enrrutador/opencode-colab-workstation.git
cd opencode-colab-workstation
git checkout kaggle-migration

pip install -e ".[dev]"
pytest tests/ -v
ruff check src/
```

- **67 tests** (core + proxy + scheduler + integración)
- Ejecutables **fuera de Kaggle** (mocks de `kagglehub`)
- Verifican: sin Colab, sin `shell=True`, sin `bash -c` / pipe-to-shell, recovery, cooldown, fingerprint, secretos fuera del store, credenciales git borradas, watchdog sin publish, checkpoint sin GitHub auto-push

---

## Limitaciones de Kaggle (cuenta gratuita)

| Límite | Implicación |
|---|---|
| Cupos semanales CPU/GPU | El runtime puede apagarse; la workstation sigue en el Dataset |
| Cada `dataset_upload` = nueva versión | Cooldown 5 min evita spam de versiones |
| Puerto local; acceso vía Jupyter Proxy | URL de sesión; regenerar en cada runtime |
| Watchdog muere con el runtime | Continuidad = bootstrap + Dataset en el siguiente kernel |

---

## Licencia

MIT — ver [`LICENSE`](LICENSE)
