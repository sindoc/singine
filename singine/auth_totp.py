"""Minimal TOTP provisioning and verification for Singine."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_ISSUER = "Singine"
DEFAULT_DIGITS = 6
DEFAULT_PERIOD = 30
DEFAULT_ALGORITHM = "SHA1"


def _b32_no_padding(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _b32_with_padding(secret: str) -> bytes:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    return base64.b32decode((secret.upper() + padding).encode("ascii"))


def generate_secret(length: int = 20) -> str:
    return _b32_no_padding(secrets.token_bytes(length))


def hotp(secret: str, counter: int, digits: int = DEFAULT_DIGITS, algorithm: str = DEFAULT_ALGORITHM) -> str:
    key = _b32_with_padding(secret)
    digest = getattr(hashlib, algorithm.lower())(b"").name
    mac = hmac.new(key, counter.to_bytes(8, "big"), digestmod=digest).digest()
    offset = mac[-1] & 0x0F
    binary = ((mac[offset] & 0x7F) << 24) | ((mac[offset + 1] & 0xFF) << 16) | ((mac[offset + 2] & 0xFF) << 8) | (mac[offset + 3] & 0xFF)
    return str(binary % (10 ** digits)).zfill(digits)


def totp(secret: str, *, for_time: Optional[int] = None, period: int = DEFAULT_PERIOD, digits: int = DEFAULT_DIGITS, algorithm: str = DEFAULT_ALGORITHM) -> str:
    timestamp = int(time.time() if for_time is None else for_time)
    return hotp(secret, timestamp // period, digits=digits, algorithm=algorithm)


def verify_totp(code: str, secret: str, *, now: Optional[int] = None, period: int = DEFAULT_PERIOD, digits: int = DEFAULT_DIGITS, algorithm: str = DEFAULT_ALGORITHM, window: int = 1) -> Dict[str, Any]:
    candidate = "".join(ch for ch in code if ch.isdigit())
    if len(candidate) != digits:
        return {"ok": False, "error": f"expected {digits} digits"}
    timestamp = int(time.time() if now is None else now)
    for delta in range(-window, window + 1):
        step_time = timestamp + (delta * period)
        expected = totp(secret, for_time=step_time, period=period, digits=digits, algorithm=algorithm)
        if hmac.compare_digest(candidate, expected):
            return {"ok": True, "code": candidate, "skew_steps": delta, "verified_at": timestamp}
    return {"ok": False, "error": "invalid code", "verified_at": timestamp}


def provisioning_uri(secret: str, *, issuer: str, account_name: str, digits: int = DEFAULT_DIGITS, period: int = DEFAULT_PERIOD, algorithm: str = DEFAULT_ALGORITHM) -> str:
    label = urllib.parse.quote(f"{issuer}:{account_name}")
    params = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": algorithm,
            "digits": digits,
            "period": period,
        }
    )
    return f"otpauth://totp/{label}?{params}"


@dataclass
class TotpProfile:
    issuer: str
    account_name: str
    secret: str
    digits: int = DEFAULT_DIGITS
    period: int = DEFAULT_PERIOD
    algorithm: str = DEFAULT_ALGORITHM
    provider_hint: str = "otp"

    def uri(self) -> str:
        return provisioning_uri(
            self.secret,
            issuer=self.issuer,
            account_name=self.account_name,
            digits=self.digits,
            period=self.period,
            algorithm=self.algorithm,
        )

    def current_code(self) -> str:
        return totp(self.secret, digits=self.digits, period=self.period, algorithm=self.algorithm)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["otpauth_uri"] = self.uri()
        return payload


def profile_from_args(args: Any) -> TotpProfile:
    state = getattr(args, "state", None)
    if state:
        path = Path(state).expanduser()
        if path.exists():
            return load_profile(path)
    return TotpProfile(
        issuer=getattr(args, "issuer", DEFAULT_ISSUER),
        account_name=getattr(args, "account_name", "user@singine.local"),
        secret=getattr(args, "secret", None) or generate_secret(),
        digits=int(getattr(args, "digits", DEFAULT_DIGITS)),
        period=int(getattr(args, "period", DEFAULT_PERIOD)),
        algorithm=str(getattr(args, "algorithm", DEFAULT_ALGORITHM)).upper(),
        provider_hint=str(getattr(args, "provider", "otp")),
    )


def save_profile(path: Path, profile: TotpProfile) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_profile(path: Path) -> TotpProfile:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TotpProfile(
        issuer=payload["issuer"],
        account_name=payload["account_name"],
        secret=payload["secret"],
        digits=int(payload.get("digits", DEFAULT_DIGITS)),
        period=int(payload.get("period", DEFAULT_PERIOD)),
        algorithm=str(payload.get("algorithm", DEFAULT_ALGORITHM)).upper(),
        provider_hint=str(payload.get("provider_hint", "otp")),
    )
