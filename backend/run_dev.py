"""Start this checkout's API with an explicit, reliable source watch directory."""
import os
from pathlib import Path

import uvicorn


if __name__ == '__main__':
    backend = Path(__file__).resolve().parent
    os.chdir(backend)
    # Polling also handles editors/filesystem layers that miss native events.
    os.environ.setdefault('WATCHFILES_FORCE_POLLING', 'true')
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000,
                reload=True, reload_dirs=[str(backend / 'app')])
