"""Where the app mark lives at runtime.

Two places can hold it, and the order matters:

1. The Flask static folder. In the container that IS the built frontend
   (`COPY --from=frontend-builder /frontend/dist /app/static`), so it carries
   whatever logo the current build ships — a re-branded or updated frontend
   wins without touching the backend.
2. A copy packaged with the backend. `backend/static` is a build-output drop
   and is git-ignored, so in a fresh checkout — CI, a dev clone — the first
   location does not exist at all.

Callers treat a missing mark as "render without it", never as an error.
"""

import os

from flask import current_app

PACKAGED_ASSETS_DIR = 'assets'
STATIC_ICONS_DIR = 'icons'


def app_mark_path(filename):
    """Absolute path to the named app mark, or None when it cannot be found."""
    static_folder = current_app.static_folder or ''
    candidates = [
        os.path.join(static_folder, STATIC_ICONS_DIR, filename),
        os.path.join(current_app.root_path, PACKAGED_ASSETS_DIR, filename),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None
