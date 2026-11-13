"""Production WSGI entrypoint discovered by Vercel's Flask framework preset."""
from app import create_app

app = create_app()
