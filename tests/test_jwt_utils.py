import hashlib


class DummyCursor:
    def execute(self, *args, **kwargs):
        self.query = args[0] if args else ""

    def fetchone(self):
        if "from users" in self.query.lower():
            # Stored SHA256 hash of the password "admin"
            hashed = hashlib.sha256(b"admin").hexdigest()
            return (1, hashed, "admin")
        return None

    def close(self):
        pass


class DummyConn:
    def cursor(self):
        return DummyCursor()

    def close(self):
        pass

    def commit(self):
        pass


def test_create_token_always_returns_str(monkeypatch):
    from backend import jwt_utils

    def fake_encode(payload, secret, algorithm):
        return b"fake-token"

    monkeypatch.setattr(jwt_utils.jwt, "encode", fake_encode)

    token = jwt_utils.create_token({"foo": "bar"})

    assert isinstance(token, str)
    assert token == "fake-token"


def test_login_handles_byte_tokens(monkeypatch):
    from backend.routers import auth

    monkeypatch.setattr("backend.routers.auth.get_connection", lambda: DummyConn())

    def fake_encode(payload, secret, algorithm):
        return b"login-token"

    monkeypatch.setattr("backend.jwt_utils.jwt.encode", fake_encode)

    response = auth.login(auth.LoginIn(username="admin", password="admin"))

    assert response == {"token": "login-token"}
