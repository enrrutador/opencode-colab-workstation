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
Windows / navegador
        │
        ▼
OpenCode Web  (local al runtime: 0.0.0.0:4096)
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
10. Iniciar OpenCode Web en `0.0.0.0:4096`  
11. Arrancar Watchdog con **restart real**  
12. Checkpoint local; remoto según política  

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
OpenCode muerto → restart real (Popen nuevo) → registrar resultado
```

- Requiere `restart_fn` real (no `lambda: None`)
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

## OpenCode Web

```text
opencode web --hostname 0.0.0.0 --port 4096
```

**Kaggle no ofrece un proxy público oficial** para puertos arbitrarios del kernel.  
OpenCode Web queda **local al runtime**. Este proyecto **no inventa** túneles ni URLs públicas.

---

## Uso rápido (Kaggle)

### 1. Preparar

1. Crear un **Kaggle Dataset privado**, p. ej. `tu-usuario/opencode-workstation-persistence`
2. En **Settings → Secrets** del notebook:
   - `NVIDIA_API_KEY`
   - `OPENCODE_CLOUD_DATASET` = `tu-usuario/opencode-workstation-persistence`
   - (opcional) `GITHUB_TOKEN`, `GITHUB_REPO`

### 2. Ejecutar

```python
!pip install -q kagglehub
!pip install -q git+https://github.com/enrrutador/opencode-colab-workstation.git@kaggle-migration

import opencode_kaggle.bootstrap as bs
info = bs.bootstrap()
print(info)
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
  "web_access": "OpenCode Web is running locally inside the Kaggle runtime at http://127.0.0.1:4096 ..."
}
```

---

## Estructura del repositorio

```text
opencode-colab-workstation/
├── src/
│   ├── opencode_cloud/          # núcleo platform-agnostic
│   │   ├── runtime.py           # detección Kaggle/local + paths
│   │   ├── secrets.py           # KaggleSecrets / EnvSecrets
│   │   ├── nvidia.py            # NIM provider (env-only key)
│   │   ├── opencode.py          # ensure Node/OpenCode + config
│   │   ├── persistence.py       # PersistentStore + KagglePersistence
│   │   ├── checkpoint.py        # política local vs remoto
│   │   ├── watchdog.py          # restart real del proceso
│   │   └── github_sync.py       # git con credenciales temporales
│   └── opencode_kaggle/         # adaptadores Kaggle
│       ├── bootstrap.py         # entry point notebook
│       ├── kaggle.py            # resolve_dataset_id
│       └── runtime.py           # helpers + mensaje de acceso web
├── tests/
│   ├── test_core.py             # unit / component
│   └── test_integration_persistence.py  # FakeKaggleHub pipeline
├── kaggle/Workstation.ipynb
├── config/opencode.json.example
├── scripts/install.sh
└── pyproject.toml               # hatchling, paquetes src/
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

- **40 tests** (core + integración con `FakeKaggleHub`)
- Ejecutables **fuera de Kaggle** (mocks de `kagglehub`)
- Verifican: sin Colab, sin `shell=True`, sin `bash -c` / pipe-to-shell, recovery, cooldown, fingerprint, secretos fuera del store, credenciales git borradas, watchdog sin publish, checkpoint sin GitHub auto-push

---

## Limitaciones de Kaggle (cuenta gratuita)

| Límite | Implicación |
|---|---|
| Cupos semanales CPU/GPU | El runtime puede apagarse; la workstation sigue en el Dataset |
| Cada `dataset_upload` = nueva versión | Cooldown 5 min evita spam de versiones |
| Sin URL pública oficial del puerto 4096 | OpenCode Web es local al kernel |
| Watchdog muere con el runtime | Continuidad = bootstrap + Dataset en el siguiente kernel |

---

## Licencia

MIT — ver [`LICENSE`](LICENSE)
