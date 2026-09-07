"""Store the Canvas token in the operating system credential store.

Resolution order for reads is environment variable, then credential store, then the
0600 file fallback. The file fallback only ever gets *written* when the student passes
``--allow-file-secrets``, and writing it prints a warning.

Nothing in this module logs a token, and no token is ever placed in a tool result.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Final

from openmind.config import home_dir

logger = logging.getLogger(__name__)

SERVICE: Final[str] = "openmind-berkeley"
ACCOUNT: Final[str] = "canvas-token"
ENV_VAR: Final[str] = "OPENMIND_CANVAS_TOKEN"


class SecretError(Exception):
    """Raised when a secret cannot be stored or retrieved."""


def _fallback_path() -> Path:
    """Return the path of the plain-file token fallback."""
    return home_dir() / "token"


NO_STORE_ENV: Final[str] = "OPENMIND_CREDENTIAL_STORE"


def keyring_available() -> bool:
    """Return whether a usable OS credential store is present."""
    # Tests and CI set this to "none" so a developer's real credential store is never
    # consulted, and never mistaken for a fixture.
    if os.environ.get(NO_STORE_ENV, "").strip().lower() == "none":
        return False
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
    except Exception:  # pragma: no cover - keyring is a hard dependency
        return False
    try:
        return not isinstance(keyring.get_keyring(), FailKeyring)
    except Exception:  # pragma: no cover - backend probing can fail on odd systems
        return False


def get_token() -> str | None:
    """Return the Canvas token from the environment, credential store, or file."""
    env_token = os.environ.get(ENV_VAR, "").strip()
    if env_token:
        return env_token

    if keyring_available():
        try:
            import keyring

            stored = keyring.get_password(SERVICE, ACCOUNT)
        except Exception:
            logger.warning("Could not read the Canvas token from the OS credential store.", exc_info=False)
        else:
            if stored and stored.strip():
                return stored.strip()

    path = _fallback_path()
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Could not read the Canvas token file.")
            return None
        if text:
            return text
    return None


def set_token(token: str, *, allow_file: bool = False) -> str:
    """Store the Canvas token and return the backend used (``keyring`` or ``file``)."""
    token = token.strip()
    if not token:
        raise SecretError("Refusing to store an empty Canvas token.")

    if keyring_available():
        try:
            import keyring

            keyring.set_password(SERVICE, ACCOUNT, token)
        except Exception as exc:
            if not allow_file:
                raise SecretError(
                    "Could not write to the OS credential store. "
                    "Re-run with --allow-file-secrets to store the token in a 0600 file instead."
                ) from exc
        else:
            _delete_file_token()
            return "keyring"
    elif not allow_file:
        raise SecretError(
            "No OS credential store is available on this machine. "
            "Re-run with --allow-file-secrets to store the token in a 0600 file instead."
        )

    path = _fallback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover - Windows
        logger.debug("Could not restrict permissions on the token file.")
    return "file"


def delete_token() -> bool:
    """Remove the Canvas token from every backend we may have written to.

    Returns whether anything was there to remove, so `openmind clear` can say
    "deleted" only when it did.
    """
    removed = False
    if keyring_available():
        try:
            import keyring

            # Backends differ on deleting a missing item (some raise, fakes do not), so
            # look first rather than read the answer from an exception.
            if keyring.get_password(SERVICE, ACCOUNT) is not None:
                keyring.delete_password(SERVICE, ACCOUNT)
                removed = True
        except Exception:
            logger.debug("No Canvas token was present in the OS credential store.")
    return _delete_file_token() or removed


def _delete_file_token() -> bool:
    """Remove the plain-file token fallback when present."""
    path = _fallback_path()
    try:
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed
    except OSError:  # pragma: no cover
        logger.debug("Could not remove the token file.")
        return False


def backend_name() -> str:
    """Return where the token currently lives, for `openmind doctor`."""
    if os.environ.get(ENV_VAR, "").strip():
        return f"environment ({ENV_VAR})"
    if keyring_available():
        try:
            import keyring

            if keyring.get_password(SERVICE, ACCOUNT):
                return f"OS credential store ({type(keyring.get_keyring()).__name__})"
        except Exception:
            pass
    if _fallback_path().exists():
        return f"file ({_fallback_path()})"
    return "not stored"


def mask(secret: str) -> str:
    """Show the first 6 and last 4 characters of a secret and mask the rest."""
    if len(secret) <= 12:
        return (secret[:3] if secret else "") + "****"
    return secret[:6] + "****" + secret[-4:]
