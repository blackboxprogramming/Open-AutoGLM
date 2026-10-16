"""Input utilities for Android device text input.

Modified by BlackRoad: bound/check input commands and restore failed selection.
"""

import base64
import subprocess
from subprocess import CalledProcessError, TimeoutExpired
from typing import Optional


INPUT_COMMAND_TIMEOUT_SECONDS = 10.0


def _run_input_command(command: list[str]) -> subprocess.CompletedProcess:
    """Bound command wait and check exit without exposing typed content."""
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=True,
            timeout=INPUT_COMMAND_TIMEOUT_SECONDS,
        )
    except TimeoutExpired:
        raise RuntimeError(
            f"ADB input command timed out after {INPUT_COMMAND_TIMEOUT_SECONDS:g} seconds"
        ) from None
    except CalledProcessError as error:
        raise RuntimeError(
            f"ADB input command failed with exit status {error.returncode}"
        ) from None


def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field using ADB Keyboard.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Note:
        Requires ADB Keyboard to be installed on the device.
        See: https://github.com/nicnocquee/AdbKeyboard
    """
    adb_prefix = _get_adb_prefix(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    _run_input_command(
        adb_prefix
        + [
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded_text,
        ],
    )


def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    _run_input_command(
        adb_prefix + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
    )


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Detect current keyboard and switch to ADB Keyboard if needed.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The original keyboard IME identifier for later restoration.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Get current IME
    result = _run_input_command(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
    )
    current_ime = result.stdout.strip()
    components = current_ime.split("/")
    if (
        len(components) != 2
        or not all(components)
        or any(character.isspace() for character in current_ime)
    ):
        raise ValueError("Cannot establish the original keyboard IME")

    try:
        # Switch to ADB Keyboard if not already set, then warm it up.
        if current_ime != "com.android.adbkeyboard/.AdbIME":
            _run_input_command(
                adb_prefix + ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"]
            )
        type_text("", device_id)
    except BaseException as selection_error:
        try:
            restore_keyboard(current_ime, device_id)
        except Exception as restore_error:
            if isinstance(selection_error, Exception):
                raise RuntimeError(
                    f"Keyboard selection failed: {selection_error}; "
                    f"restoration failed: {restore_error}"
                ) from selection_error
        raise

    return current_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore the original keyboard IME.

    Args:
        ime: The IME identifier to restore.
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    _run_input_command(
        adb_prefix + ["shell", "ime", "set", ime],
    )


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
