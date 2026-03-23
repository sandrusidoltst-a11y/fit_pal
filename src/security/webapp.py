from fastapi import FastAPI

from src.security.internal_auth_middleware import InternalTokenMiddleware

app = FastAPI()
app.add_middleware(InternalTokenMiddleware)
