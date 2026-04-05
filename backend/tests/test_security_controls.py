from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "false")
os.environ.setdefault("JWT_SECRET_KEY", "anomalyguard-test-jwt-0123456789abcdef0123456789")
os.environ.setdefault("ADMIN_USERNAME", "test-admin")
os.environ.setdefault("ADMIN_PASSWORD", "AnomalyGuardTestAdmin!2026")
os.environ.setdefault("DEVICE_API_KEY", "anomalyguard-test-device-key-0123456789")
os.environ.setdefault("CORS_ALLOW_ORIGINS", "http://testserver")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEPS_ROOT = BACKEND_ROOT / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

from app.config import Settings
from app.services import device_auth


class SecurityControlTests(unittest.TestCase):
    def test_settings_rejects_wildcard_cors_in_strict_mode(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                jwt_secret_key="anomalyguard-config-jwt-0123456789abcdef0123456789",
                admin_password="AnomalyGuardConfigAdmin!2026",
                device_api_key="anomalyguard-config-device-key-0123456789",
                cors_allow_origins="*",
            )

    def test_settings_accepts_device_registry_path_in_strict_mode(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write('{"esp32-device-001":"anomalyguard-device-esp32-001-32char-local"}')
            registry_path = handle.name

        try:
            settings = Settings(
                jwt_secret_key="anomalyguard-config-jwt-0123456789abcdef0123456789",
                admin_password="AnomalyGuardConfigAdmin!2026",
                device_api_key="",
                device_keys_path=registry_path,
                cors_allow_origins="http://localhost:5173",
            )
        finally:
            Path(registry_path).unlink(missing_ok=True)

        self.assertEqual(settings.device_keys_path, registry_path)

    def test_settings_resolves_device_registry_relative_to_backend_root(self) -> None:
        settings = Settings(
            jwt_secret_key="anomalyguard-config-jwt-0123456789abcdef0123456789",
            admin_password="AnomalyGuardConfigAdmin!2026",
            device_api_key="",
            device_keys_path="secrets.example/device_keys.json.example",
            cors_allow_origins="http://localhost:5173",
        )

        self.assertTrue(settings.device_keys_path.endswith("backend\\secrets.example\\device_keys.json.example"))

    def test_settings_resolves_jwt_secret_from_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            handle.write("anomalyguard-file-jwt-0123456789abcdef0123456789")
            jwt_secret_path = handle.name

        try:
            settings = Settings(
                jwt_secret_key="",
                jwt_secret_key_file=jwt_secret_path,
                admin_password="AnomalyGuardConfigAdmin!2026",
                device_api_key="anomalyguard-config-device-key-0123456789",
                cors_allow_origins="http://localhost:5173",
            )
        finally:
            Path(jwt_secret_path).unlink(missing_ok=True)

        self.assertEqual(settings.jwt_secret_key, "anomalyguard-file-jwt-0123456789abcdef0123456789")

    def test_validate_device_key_uses_station_registry_when_configured(self) -> None:
        with patch.object(device_auth, "load_device_key_registry", return_value={"esp32-device-001": "device-key-001"}):
            device_auth.validate_device_key("esp32-device-001", "device-key-001")
            with self.assertRaises(HTTPException):
                device_auth.validate_device_key("esp32-device-002", "device-key-001")
            with self.assertRaises(HTTPException):
                device_auth.validate_device_key("esp32-device-001", "wrong-key")

    def test_validate_device_key_falls_back_to_shared_key_when_registry_is_empty(self) -> None:
        with patch.object(device_auth, "load_device_key_registry", return_value={}), patch.object(
            device_auth.settings,
            "device_api_key",
            "shared-device-key-0123456789",
        ):
            device_auth.validate_device_key("esp32-device-001", "shared-device-key-0123456789")
            with self.assertRaises(HTTPException):
                device_auth.validate_device_key("esp32-device-001", "wrong-key")
