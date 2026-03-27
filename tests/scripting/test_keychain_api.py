"""Tests for wz.keychain encrypted vault API."""

from unittest.mock import patch

import pytest


MOCK_MASTER_KEY_B64 = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="  # 32 bytes b64


class TestKeychainAPIInit:
    @patch("wenzi.scripting.api.keychain.keychain_get", return_value=MOCK_MASTER_KEY_B64)
    def test_loads_existing_master_key(self, mock_get, tmp_path):
        from wenzi.scripting.api.keychain import KeychainAPI

        api = KeychainAPI(vault_path=str(tmp_path / "keychain.json"))
        assert api._master_key is not None
        assert len(api._master_key) == 32
        mock_get.assert_called_once_with("scripting.vault.master_key")

    @patch("wenzi.scripting.api.keychain.keychain_set", return_value=True)
    @patch("wenzi.scripting.api.keychain.keychain_get", return_value=None)
    def test_generates_master_key_when_absent(self, mock_get, mock_set, tmp_path):
        from wenzi.scripting.api.keychain import KeychainAPI

        api = KeychainAPI(vault_path=str(tmp_path / "keychain.json"))
        assert api._master_key is not None
        assert len(api._master_key) == 32
        mock_set.assert_called_once()
        import base64
        stored_b64 = mock_set.call_args[0][1]
        assert len(base64.b64decode(stored_b64)) == 32

    @patch("wenzi.scripting.api.keychain.keychain_set", return_value=False)
    @patch("wenzi.scripting.api.keychain.keychain_get", return_value=None)
    def test_degrades_when_keychain_unavailable(self, mock_get, mock_set, tmp_path):
        from wenzi.scripting.api.keychain import KeychainAPI

        api = KeychainAPI(vault_path=str(tmp_path / "keychain.json"))
        assert api._master_key is None
