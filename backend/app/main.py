"""
Public-facing chat backend for the CV agent.

Hirers hit /chat/stream with a message; this calls the model with tool
definitions mirroring search_cv() / get_full_entry(), executes them locally, and
streams the model's answer back.

The module is only the ASGI entrypoint — `uvicorn app.main:app`, which the
Dockerfile and both compose files name. Everything it is made of lives in
`app/factory.py`, so that importing the factory does not read the environment
and a test can build an application without one.
"""
from app.factory import create_app

app = create_app()
