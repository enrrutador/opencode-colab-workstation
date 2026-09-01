# OpenCode Colab Workstation — Drive + NVIDIA NIM + GitHub

Workstation persistente / reanudable para **OpenCode** en **Google Colab** con persistencia en Google Drive, **NVIDIA NIM** como provider y sincronización con **GitHub**.

Basado en `workstation v4 - SIN AUTENTICACIÓN WEB`.

> **⚠️ ADVERTENCIA DE SEGURIDAD:** Esta versión desactiva la autenticación web de OpenCode (`permission: allow` + sin `OPENCODE_SERVER_PASSWORD`) y expone el acceso via `google.colab.kernel.proxyPort(4096)`. Cualquiera con el enlace del proxy tiene control total de la VM. Úsalo solo en Colab privado. Para uso compartido, activa auth (ver `config/opencode.json.example`).

## Características

- Google Drive persistente (`/content/drive/MyDrive/opencode_colab`)
- Historial, sesiones, mensajes, workspace y config persistentes (`rsync -a`)
- NVIDIA NIM con autodetección de modelos (`/v1/models`, prefiere `nemotron`)
- GitHub sync automático (fetch/merge/push con `credential.helper store`)
- OpenCode Web automático en `0.0.0.0:4096` via proxy nativo de Colab
- Watchdog + backup cada 180s + backup en `SIGTERM`

## Estructura

```
colab/workstation_v4.py   # celda original monolítica (referencia)
src/opencode_colab/       # versión modularizada (recomendada para desarrollo)
  drive.py                # mount y detección de MyDrive
  persistence.py          # sync_dir, backup_all, runtime.json
  nvidia.py               # consulta /v1/models y selección
  opencode.py             # instalación y config opencode.json
  github_sync.py          # git init / remote / push
  watchdog.py             # hilo de supervisión
config/opencode.json.example
scripts/install.sh
```

## Inicio rápido (Colab)

1. Crea un repo vacío en GitHub (este repo ya está creado).
2. En Colab, monta Drive y ejecuta:

```python
# Opción A: usar la celda original
%run colab/workstation_v4.py

# Opción B: modular (recomendada)
!pip install -e .
python -m opencode_colab --github-repo https://github.com/TU_USUARIO/TU_REPO
```

Te pedirá:
- `NVIDIA_API_KEY` → genera en https://build.nvidia.com/api-keys (`nvapi-...`)
- `GITHUB_REPO` (HTTPS) y `GITHUB_TOKEN` (`ghp_...` con scope `repo`)

Se guardan en `MyDrive/opencode_colab/secrets/credentials.json` (chmod 600) para siguientes ejecuciones.

## Configuración

Variables de entorno soportadas (tienen prioridad sobre `credentials.json`):

```bash
NVIDIA_API_KEY=nvapi-...
GITHUB_REPO=https://github.com/usuario/repo.git
GITHUB_TOKEN=ghp_...
```

Edita `~/.config/opencode/opencode.json` si necesitas cambiar `provider.nvidia.baseURL` o `model`.

## Instalación local (desarrollo)

```bash
pip install -e ".[dev]"
ruff check src/
```

## Roadmap v5 (sugerido)

- [ ] Cambiar `shell=True` + `f-string` por `subprocess.run([...], shell=False)` para evitar inyección
- [ ] Usar `google.colab.userdata` para secretos en lugar de `input()`
- [ ] Hacer `permission` y `web auth` configurables
- [ ] Cachear `apt`/`node` para no reinstalar en cada reinicio
- [ ] Añadir `healthcheck` HTTP además de `port_open`
- [ ] Retención de backups y manejo de `rsync --delete` seguro

## Licencia

MIT — ver `LICENSE`
