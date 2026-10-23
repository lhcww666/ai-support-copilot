from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings

ROLE_LEVEL = {"viewer": 1, "operator": 2, "admin": 3}


class AuthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class User:
    username: str
    display_name: str
    role: str


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._users = {
            "admin": (User("admin", "知识库管理员", "admin"), settings.admin_password),
            "operator": (User("operator", "客服专员", "operator"), settings.operator_password),
            "viewer": (User("viewer", "只读用户", "viewer"), settings.viewer_password),
        }

    def login(self, username: str, password: str) -> str:
        account = self._users.get(username)
        if account is None or not hmac.compare_digest(account[1], password):
            raise AuthError("用户名或密码错误")
        user = account[0]
        now = int(time.time())
        payload = {
            "sub": user.username,
            "name": user.display_name,
            "role": user.role,
            "iat": now,
            "exp": now + self.settings.token_ttl_seconds,
        }
        return self._encode(payload)

    def decode(self, token: str) -> User:
        try:
            header, payload, signature = token.split(".")
            if not hmac.compare_digest(signature, self._signature(f"{header}.{payload}")):
                raise AuthError("Token 签名无效")
            claims = json.loads(self._b64decode(payload))
            if int(claims["exp"]) < int(time.time()):
                raise AuthError("Token 已过期")
            role = str(claims["role"])
            if role not in ROLE_LEVEL:
                raise AuthError("Token 角色无效")
            return User(str(claims["sub"]), str(claims["name"]), role)
        except AuthError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuthError("Token 格式无效") from exc

    def can_access_visibility(self, user: User, visibility: str) -> bool:
        if visibility == "public":
            return True
        if visibility == "internal":
            return ROLE_LEVEL[user.role] >= ROLE_LEVEL["operator"]
        if visibility == "admin":
            return user.role == "admin"
        return False

    def require_role(self, user: User, minimum: str) -> None:
        if ROLE_LEVEL[user.role] < ROLE_LEVEL[minimum]:
            raise AuthError(f"需要 {minimum} 权限")

    def _encode(self, payload: dict[str, Any]) -> str:
        header = self._b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body = self._b64encode(json.dumps(payload, separators=(",", ":")).encode())
        return f"{header}.{body}.{self._signature(f'{header}.{body}')}"

    def _signature(self, value: str) -> str:
        digest = hmac.new(
            self.settings.app_secret.encode(),
            value.encode(),
            hashlib.sha256,
        ).digest()
        return self._b64encode(digest)

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    @staticmethod
    def _b64decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
