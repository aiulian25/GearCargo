# GearCargo — reference config

Most people don't need anything in here. The standard install lives in the repo
root: **`docker-compose.yml`** (pulls the ready single image) + **`.env.example`**,
driven by **`setup.sh`**. See the main README.

| File | What it is |
|------|-----------|
| **`.env.reference`** | The complete, documented list of **every** environment variable GearCargo supports (external DB/Redis, Ollama AI, GeoIP, tuning, domain-based access control, etc.). The root `.env.example` is the short version — copy anything extra you need from here. |

### Notes
- **Build the image yourself** instead of pulling: use the root
  `docker-compose.dev.yml` (dev / build-from-source).
- **Custom port / Synology:** no separate compose — set `APP_PORT` in your `.env`.
- **Resource limits:** the standard `docker-compose.yml` omits hard caps so it
  stays portable (Synology kernels lack the CPU CFS scheduler). Add a
  `deploy.resources.limits` block if you want them.
