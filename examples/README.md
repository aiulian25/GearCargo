# GearCargo — advanced / reference configs

Most people don't need anything in here. The standard install lives in the repo
root: **`docker-compose.yml`** (pulls the ready single image) + **`.env.example`**,
driven by **`setup.sh`**. See the main README.

Use these only for specific needs:

| File | When to use |
|------|-------------|
| **`docker-compose.4container.yml`** | You want strict process isolation between the app, PostgreSQL and Redis (three separate containers with per-service `cap_drop`, `read_only` rootfs, and hard resource limits). Builds locally. The 4-container image is also published as `ghcr.io/aiulian25/gearcargo:multi`. |
| **`.env.reference`** | The complete, documented list of **every** environment variable GearCargo supports (external DB/Redis, Ollama AI, GeoIP, tuning, domain-based access control, etc.). The root `.env.example` is the short version; copy anything you need from here. |

### Notes
- **Build the single image yourself** instead of pulling: use the root
  `docker-compose.single.yml` (dev / build-from-source), not a file here.
- **Custom port / Synology:** you don't need a separate compose — just set
  `APP_PORT` in your `.env` (e.g. `APP_PORT=5050`).
- **Resource limits:** the standard `docker-compose.yml` omits hard limits so it
  stays portable (Synology kernels lack the CPU CFS scheduler). Copy the
  `deploy.resources` block from `docker-compose.4container.yml` if you want caps.
- **Security:** none of these weaken the defaults — the 4-container file is the
  *more* isolated option (see `SECURITY_ASSESSMENT.md` §3/§9).
