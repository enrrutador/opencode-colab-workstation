# OpenCode Cloud Workstation

**Workstation de desarrollo persistente y reanudable para OpenCode sobre Kaggle.**

El runtime es reemplazable; la workstation no.

Un kernel Kaggle puede morir, reiniciarse o desaparecer. El trabajo del usuario **no** debe desaparecer con él.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version: v5](https://img.shields.io/badge/version-v5-blue.svg)]()

> Migración completa desde Colab. **No hay dependencia de Google Colab ni Google Drive.**  
> Runtime objetivo: **Kaggle Kernels**. Persistencia: **Kaggle Dataset**. Secretos: **Kaggle Secrets**. Código versionado: **GitHub**.

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
        ├── /kaggle/working/opencode_cloud/     ← almacenamiento local temporal
        │        ├── workspace
        │        ├── state
        │        ├── config
        │        ├── checkpoints
        │        ├── metadata
        │        └── logs
        │
        ├── Kaggle Dataset                      ← persistencia de la workstation
        ├── GitHub                              ← versionado del código
        ├── Kaggle Models                       ← modelos/weights (cuando corresponda)
        └── Kaggle Secrets                      ← API keys
```

### Separación de responsabilidades

| Componente | Responsabilidad |
|---|---|
| **Kaggle Dataset** | Persistencia de la workstation (estado, workspace, config sin secretos) |
| **GitHub** | Versionado de código (commits, historial) |
| **Kaggle Models** | Artefactos / pesos de modelo |
| **Kaggle Secrets** | Secretos (NVIDIA_API_KEY, GITHUB_TOKEN, …) |
| **/kaggle/working** | Solo temporal del runtime actual |

**Importante:** `/kaggle/datasets/...` **no** se trata como filesystem escribible.  
La persistencia remota usa exclusivamente:

```text
kagglehub.dataset_download()  →  restore local
kagglehub.dataset_upload()    ←  publish desde staging local
```

## Flujo de recovery (runtime nuevo)

1. Detectar Kaggle  
2. Inicializar `/kaggle/working/opencode_cloud/`  
3. Cargar secretos (`UserSecretsClient`)  
4. Identificar Dataset (`OPENCODE_CLOUD_DATASET`)  
5. `dataset_download`  
6. Validar workstation  
7. Restaurar workspace / config / estado  
8. Asegurar Node + OpenCode (idempotente)  
9. Configurar NVIDIA NIM (solo env)  
10. Iniciar OpenCode Web local  
11. Watchdog (reinicio real del proceso)  
12. Checkpoints locales + remotos según política  

Estados de recovery:

- `RESTORED_FROM_DATASET` — restauración válida  
- `FRESH_WORKSTATION` — no existe Dataset aún (o está vacío)  
- `RESTORE_FAILED` — Dataset presente pero inválido/corrupto (**no se finge éxito**)

## Checkpoints (dos niveles)

**Nivel 1 — Local** (barato, frecuente)  
Guarda bajo `/kaggle/working/opencode_cloud/`. **No** crea versión de Dataset.

**Nivel 2 — Remoto** (caro, con política)  
Publica al Kaggle Dataset. Política:

- cooldown mínimo **5 minutos** entre publicaciones normales  
- cambios significativos pendientes  
- shutdown ordenado → publicar ya  
- checkpoint explícito → publicar ya  

`CheckpointManager` decide *si* publicar.  
`KagglePersistence` ejecuta la publicación.

## Watchdog

Solo vigila el proceso OpenCode:

```text
OpenCode muerto → restart real → registrar resultado
```

No publica Dataset, no hace `git push`, no es el sistema de persistencia.

## Secretos

```python
from kaggle_secrets import UserSecretsClient
```

Esperados:

- `NVIDIA_API_KEY` (requerido)  
- `GITHUB_TOKEN` (opcional)  
- `OPENCODE_CLOUD_DATASET` puede vivir como secreto o como variable de entorno (configuración)

Los secretos **no** se escriben en:

- Dataset  
- workspace  
- config de OpenCode  
- logs  
- archivos de credenciales persistentes  

La config de OpenCode usa `{env:NVIDIA_API_KEY}`.

## GitHub

Solo versionado de código. Credenciales **temporales**:

1. crear archivo temporal  
2. usar credential helper  
3. ejecutar git  
4. **eliminar** el archivo en `finally` (también si git falla)

No hay `.git-credentials` persistente ni `credentials.json` con token.

## OpenCode Web

Se inicia en el runtime:

```text
opencode web --hostname 0.0.0.0 --port 4096
```

**Kaggle no ofrece un proxy público oficial** para puertos arbitrarios del kernel.  
OpenCode Web está disponible **localmente dentro del runtime**. No se inventan túneles ni URLs públicas.

## Uso rápido

1. Dataset privado: `owner/opencode-workstation-persistence`  
2. Secrets: `NVIDIA_API_KEY`, `OPENCODE_CLOUD_DATASET`, opcionalmente GitHub  
3. En un kernel:

```python
!pip install kagglehub
!pip install git+https://github.com/enrrutador/opencode-colab-workstation.git@kaggle-migration

import opencode_kaggle.bootstrap as bs
info = bs.bootstrap()
print(info)
```

O usa el notebook `kaggle/Workstation.ipynb`.

## Paquetes

```text
src/opencode_cloud/     # núcleo (runtime, store, persistence, checkpoint, watchdog, …)
src/opencode_kaggle/    # adaptadores Kaggle + bootstrap
```

Ambos son paquetes Python válidos; `pyproject.toml` los declara con hatchling.  
No se usa `sys.path.insert` en el código de producción.

## Desarrollo y tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/
```

Los tests usan mocks de `kagglehub` y pueden ejecutarse **fuera de Kaggle**.

## Limitaciones de Kaggle (gratuitas)

- Kernels: cupos semanales de CPU/GPU  
- Dataset: cada publish remoto = nueva versión  
- No hay URL pública para servicios en el kernel  
- El watchdog no sobrevive a la muerte del runtime; la recovery es por bootstrap + Dataset  

## Licencia

MIT — ver `LICENSE`
