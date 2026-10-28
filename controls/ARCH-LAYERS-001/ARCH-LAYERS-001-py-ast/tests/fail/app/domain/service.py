from app.infrastructure.client import Client


def load() -> Client:
    return Client()
