import os
import datetime
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "secret")


def create_token(data: dict, expires_seconds: int = 3600) -> str:
    payload = data.copy()
    payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_seconds)
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    # PyJWT 1.x returns the encoded token as ``bytes`` which FastAPI cannot
    # serialise in JSON responses. Normalise the return type to ``str`` so the
    # caller never has to worry about the library version being used.
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
