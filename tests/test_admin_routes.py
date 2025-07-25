import importlib
import sys
import os

import pytest
from fastapi.testclient import TestClient


class DummyCursor:
    def execute(self, *args, **kwargs):
        self.query = args[0] if args else ""

    def fetchone(self):
        if "FROM users" in self.query:
            # bcrypt hash for 'admin'
            return [1, "$2b$12$Y.DzD5azTaGBSLNfQCbwGOpVxBmWncTZyjNOyPNJwzLneHpIh9DO2", "admin"]
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class DummyConn:
    def cursor(self):
        return DummyCursor()

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.fixture()
def client(monkeypatch):
