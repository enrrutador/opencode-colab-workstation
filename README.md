# OpenCode Cloud Workstation

**Workstation de desarrollo remoto persistente y reanudable para OpenCode sobre Kaggle.**
No es simplemente “OpenCode instalado en Kaggle”: es una arquitectura completa de workstation cloud con persistencia, checkpoints, recuperación, watchdog, sincronización con GitHub y gestión de secretos, utilizando únicamente servicios gratuitos de Kaggle y GitHub.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version: v5](https://img.shields.io/badge/version-v5-blue.svg)]()

> **Migración desde Colab → Kaggle**
> Este proyecto fue reescrito desde cero para eliminar toda dependencia de Google Colab / Google Drive. El runtime objetivo es **Kaggle Kernels** con persistencia en **Kaggle Datasets**, secretos en **Kaggle Secrets**, versiones en **GitHub** y modelos en **Kaggle Models**.

## Qué resuelve

Kaggle proporciona un runtime efímero gratuito. Esta workstation añade:

- **Bootstrap idempotente** del runtime Kaggle
- **Persistencia gestionada** en Kaggle Dataset
- **Checkpoints controlados** y publicación selectiva
- **Recuperación automática** tras muerte del runtime
- **Watchdog** para reinicio del proceso OpenCode
- **Sincronización segura con GitHub**
- **Gestión de secretos** vía Kaggle Secrets
- **OpenCode Web** listo para uso remoto

El runtime es reemplazable; la workstation no.

## Arquitectura

```
Client
  ↓
OpenCode Web
  ↓
Kaggle Runtime
  ↓
Persistence Layer
  ├── Kaggle Dataset  (workspace, estado, checkpoints)
  ├── GitHub          (código versionado)
  ├── Kaggle Models   (artefactos de modelo, opcional)
  └── Kaggle Secrets  (NVIDIA_API_KEY, GITHUB_TOKEN)
```

### Componentes

- `src/opencode_cloud/` — núcleo agnóstico de plataforma
  - `runtime.py` — detección de runtime y rutas
  - `secrets.py` — abstracción de secretos
  - `persistence.py` — capa de persistencia
  - `checkpoint.py` — estrategia de checkpoints
  - `github_sync.py` — sincronización segura
  - `nvidia.py` — provider NVIDIA NIM
  - `opencode.py` — bootstrap de OpenCode
  - `watchdog.py` — monitoreo de proceso
- `src/opencode_kaggle/` — adaptadores específicos de Kaggle
  - `kaggle.py` — integración con Datasets
  - `runtime.py` — detección de kernel Kaggle
  - `bootstrap.py` — entrada de notebook

## Uso rápido en Kaggle

1. Crea un Kaggle Dataset privado `owner/opencode-workstation-persistence`
2. En Kaggle Secrets, define:
   - `NVIDIA_API_KEY`
   - `GITHUB_REPO` (opcional)
   - `GITHUB_TOKEN` (opcional)
   - `OPENCODE_CLOUD_DATASET` = `owner/opencode-workstation-persistence`
3. En un nuevo Kaggle Kernel, instala el paquete:

```python
!pip install git+https://github.com/enrrutador/opencode-colab-workstation
```

4. Bootstrap:

```python
import opencode_kaggle.bootstrap as bs
info = bs.bootstrap()
print(info)
```

OpenCode Web se iniciará en `http://localhost:4096`. Kaggle no expone URLs públicas para puertos internos; consulta la sección de limitaciones.

## Persistencia

Persistencia remota se realiza en un Kaggle Dataset:

```
/kaggle/datasets/owner/dataset/
├── state/
│   ├── opencode/      # ~/.local/share/opencode
│   ├── config/        # ~/.config/opencode
│   └── runtime/       # metadata.json
├── workspace/         # código del usuario
├── logs/              # logs importantes
└── checkpoints/       # snapshots de recuperación
```

El runtime efímero vive en `/kaggle/working`.

## Checkpoints

Dos conceptos separados:

- **Checkpoint local**: rápido, frecuente, no publica.
- **Persistencia remota**: publicación controlada al Dataset con criterios:
  - Intervalo mínimo 5 minutos
  - Cambios significativos detectados
  - Cierre ordenado o recuperación

Esto evita crear una nueva versión de Dataset cada 180 segundos.

## Recuperación

Al iniciar un nuevo runtime:

1. Bootstrap
2. Obtener secretos desde Kaggle Secrets
3. Descargar último estado persistente desde Dataset
4. Restaurar workspace, configuración y estado de OpenCode
5. Validar e iniciar OpenCode

Si el runtime anterior murió inesperadamente, se restaura el último checkpoint disponible.

## Secrets

Se utiliza `Kaggle Secrets` como fuente principal. Nunca se escriben a disco en texto plano, nunca se imprimen en logs y nunca se pasan como argumentos de shell.

## GitHub

Sincronización de código vía Git HTTPS con credential helper `store` y archivo protegido `chmod 600`. Comandos construidos sin `shell=True` donde es posible para evitar inyección.

## OpenCode Web

OpenCode se lanza con `--hostname 0.0.0.0 --port 4096` sin autenticación web (`permission: allow`). Kaggle limita el acceso remoto a puertos internos; el acceso típico es vía la interfaz de Kaggle o túnel externo. No se reutiliza ningún mecanismo de Colab.

## Límites gratuitos de Kaggle

- **Kernels**: 60 horas/semana en CPU, 20 horas/semana en GPU.
- **Datasets**: lectura/escritura via API; cambios persistentes requieren publicar versión del Dataset.
- **Secrets**: 50 secretos por cuenta.
- **Modelos**: Kaggle Models permite subir modelos; uso limitado.
- No hay URL pública para servicios web internos del kernel.

## Limitaciones conocidas

- Kaggle no expone URLs públicas para servicios que escuchen en el kernel. OpenCode Web solo es accesible localmente.
- Publicar Dataset genera una nueva versión; la estrategia de checkpoint evita publicaciones excesivas.
- El watchdog no sobrevive a la muerte del runtime; la recuperación es por bootstrap.

## Desarrollo

```bash
pip install -e ".[dev]"
ruff check src/
pytest tests/
```

## Licencia

MIT — ver `LICENSE`
