"""Production entry point; no reload, credentials, migrations, or seeding."""
import os
from pathlib import Path

import uvicorn


if __name__ == '__main__':
    os.chdir(Path(__file__).resolve().parent)
    os.environ['APP_ENV'] = 'production'
    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.environ.get('PORT', '8000')))
