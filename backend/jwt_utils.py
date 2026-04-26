import os
import datetime
import jwt

JWT_SECRET = os.environ["JWT_SECRET"]


def create_token(data: dict, expires_seconds: int = 3600) -> str:
    payload = data.copy()
    payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_seconds)
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
