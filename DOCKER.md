# Docker setup for Power Socket

This setup reuses the existing local Ollama container, image, and model
volume. It does not download models during project setup. The existing
container is named `cavde-connect-ollama` and is not configured to restart
automatically.

## Resource safeguards

- Container memory limit: 512 MiB.
- CPU limit: 1 core.
- Only one model loaded and one parallel request.
- Ollama is exposed only on 127.0.0.1:11434.
- Model data is stored in the existing external volume `ollama_ollama_data`.

## Start (only when Windows has enough free RAM)

From PowerShell:

```powershell
docker start cavde-connect-ollama
```

Check available models:

```powershell
docker exec cavde-connect-ollama ollama list
```

Configure the Default profile in Power Socket:

- Provider: `ollama`
- Endpoint: `http://127.0.0.1:11434`
- Model: `smollm2:135m` (smallest installed option)

Stop the container when finished:

```powershell
docker stop cavde-connect-ollama
```

Do not remove the container or use `docker volume rm ollama_ollama_data`:
the external volume contains existing local model data. The Compose file is a
recreation reference; the existing container must be stopped/renamed before a
new Compose-managed container can use the same container name.

## Current limitation

The container is intentionally not started automatically. Check Windows
available RAM before starting inference. A 512 MiB container cap does not guarantee
that Windows itself has enough free memory for the Docker VM and other apps.
