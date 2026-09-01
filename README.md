# OpenCode Colab Workstation

**Workstation persistente y reanudable para OpenCode en Google Colab** con Google Drive, NVIDIA NIM y GitHub. Una sola celda, listo para usar.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/enrrutador/opencode-colab-workstation/blob/main/colab/Workstation.ipynb)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version: v4](https://img.shields.io/badge/version-v4-blue.svg)]()

> **Basado en `workstation v4 - SIN AUTENTICACIÓN WEB`**

## Cómo usar en 30 segundos (fácil)

### Opción 1: Un click (recomendada)

1. Abre este notebook en Colab: **colab/Workstation.ipynb** (botón de arriba)
2. Ejecuta la única celda (`Runtime > Run all`)
3. Pega cuando te pida:
   - `NVIDIA_API_KEY` → consíguela en https://build.nvidia.com/api-keys (empieza con `nvapi-...`)
   - `GITHUB_REPO` → `https://github.com/tu-usuario/tu-repo.git` (puede ser este mismo repo)
   - `GITHUB_TOKEN` → https://github.com/settings/tokens/new (marca `repo`)
4. Click en **🚀 ABRIR OPENCODE** (enlace verde que aparece al final)

Listo. No hay que ejecutar nada más.

### Opción 2: Clonar este repo en Colab

```python
!git clone https://github.com/enrrutador/opencode-colab-workstation.git
%run opencode-colab-workstation/colab/workstation_v4.py
```

## Qué hace automáticamente (12 pasos)

1. Monta Google Drive (`/content/drive`)
2. Crea estructura persistente en `MyDrive/opencode_colab/`:
   - `state/opencode/` → historial completo de OpenCode
   - `state/config/` → `~/.config/opencode/`
   - `workspace/` → tu código (`/content/opencode_runtime/workspace`)
   - `backups/`, `logs/`, `secrets/credentials.json`
3. Restaura estado previo si existe (rsync)
4. Instala dependencias (`git`, `jq`, `rsync`, `Node.js 22`, `opencode-ai`)
5. Configura `NVIDIA NIM` (`https://integrate.api.nvidia.com/v1`) y autodetecta modelos (prefiere `nemotron`)
6. Escribe `~/.config/opencode/opencode.json` con `permission: allow` y `model: nvidia/...`
7. Configura Git (`user.name`, `credential.helper store`)
8. Sincroniza workspace con GitHub (`fetch` + `merge` + `push`)
9. Inicia `opencode web --hostname 0.0.0.0 --port 4096` sin usuario/contraseña
10. Genera enlace con `google.colab.kernel.proxyPort(4096)` (proxy nativo, sin Cloudflare/VNC)
11. Guarda `state/runtime.json` y activa watchdog (reinicia OpenCode si muere) + backup cada 180s
12. Muestra panel verde con botón para abrir OpenCode Web

## Dónde queda cada cosa

| En Colab (efímero) | En Drive (persistente) |
|---|---|
| `/content/opencode_runtime/workspace` | `MyDrive/opencode_colab/workspace/` |
| `~/.local/share/opencode/` | `MyDrive/opencode_colab/state/opencode/` |
| `~/.config/opencode/` | `MyDrive/opencode_colab/state/config/` |
| `/content/opencode_runtime/logs/opencode-web.log` | `MyDrive/opencode_colab/logs/` |

Si Colab se reinicia, al volver a ejecutar la celda se restaura todo.

## Configuración

No necesitas editar archivos. La primera vez te pide los secretos por `input()` y los guarda en `MyDrive/opencode_colab/secrets/credentials.json` (chmod 600).

Para siguientes ejecuciones puedes también usar variables de entorno (tienen prioridad):

```bash
NVIDIA_API_KEY=nvapi-...
GITHUB_REPO=https://github.com/usuario/repo.git
GITHUB_TOKEN=ghp_...
```

Para cambiar de modelo, edita `credentials.json` (`nvidia_model`) o borra esa clave y vuelve a ejecutar.

## Estructura del repo

```
.
├── colab/
│   ├── Workstation.ipynb      # Notebook listo para "Open in Colab" (1 celda)
│   └── workstation_v4.py      # Código monolítico original (copiar/pegar)
├── src/opencode_colab/        # Versión modular para desarrollo
│   ├── drive.py
│   ├── persistence.py
│   ├── nvidia.py
│   ├── opencode.py
│   ├── github_sync.py
│   └── watchdog.py
├── config/
│   └── opencode.json.example  # Ejemplo con NVIDIA NIM
├── scripts/
│   └── install.sh             # Instalación de dependencias
└── .github/workflows/lint.yml
```

## Requisitos

- Cuenta de Google (Drive + Colab)
- NVIDIA API Key: https://build.nvidia.com/api-keys
- GitHub repo + PAT con `repo` (https://github.com/settings/tokens/new) — opcional pero recomendado para persistir código fuera de Drive

## Seguridad

> **⚠️ Sin autenticación web:** `opencode web` se lanza sin `OPENCODE_SERVER_PASSWORD` y con `permission: allow`. El proxy de Colab genera una URL única y difícil de adivinar, pero quien la tenga tiene control total. No compartas el enlace. Para añadir auth, define `OPENCODE_SERVER_PASSWORD` antes de lanzar o edita `src/opencode_colab/opencode.py`.

El token de GitHub se guarda en `git_credentials` con `store --file` y en `credentials.json` en Drive. No lo commitees.

## Solución de problemas

- **No monta Drive:** Verifica que no tengas 4 mounts ocupados (`/content/drive`, `/content/gdrive`...). Reinicia runtime.
- **OpenCode no inicia:** Mira `MyDrive/opencode_colab/logs/` o `/content/opencode_runtime/logs/opencode-web.log` (últimas 12000 líneas se imprimen al fallar)
- **GitHub no sincroniza:** Verifica `GITHUB_REPO` HTTPS y que el PAT tenga `repo`. El push falla silenciosamente y avisa `⚠ GitHub no pudo sincronizarse todavía`
- **Modelo no aparece:** Verifica `NVIDIA_API_KEY` y que tengas acceso a NIM en build.nvidia.com

## Desarrollo local

```bash
pip install -e ".[dev]"
ruff check src/
```

## Licencia

MIT — ver `LICENSE`
