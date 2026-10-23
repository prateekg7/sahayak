"""The 'settings' MCP tool for managing assistant preferences and module toggles (T13.3)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.flags import get_user_preference_service
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.core.profiles import BUNDLE_PROFILES

logger = logging.getLogger(__name__)

SETTINGS_DESCRIPTION = (
    "Manage assistant settings and toggle individual modules on or off. "
    "Use when the user says 'What are my settings?', 'Disable finance', or 'Enable business'. "
    "Do not use for setting habit or study targets; use the respective tools instead."
)

ALL_KNOWN_MODULES = set(BUNDLE_PROFILES["full"])


class SettingsRequest(BaseModel):
    """Input payload for the settings tool."""

    action: str = Field(
        default="status",
        description="Action to perform: 'status', 'enable_module', or 'disable_module'.",
    )
    module: str | None = Field(
        default=None,
        description="Target module identifier, e.g. 'finance', 'health', 'academics'.",
    )
    request_id: str | None = Field(default=None, description="Optional idempotency key.")


@requires()
@idempotent(tool_name="settings")
@instrument_tool("settings", "settings")
async def settings(
    action: str = "status",
    module: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Inspect or update user module toggles and personal assistant settings."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to manage assistant settings.",
            detail="Account linking required for settings tool",
        )

    try:
        req = SettingsRequest(action=action, module=module, request_id=request_id)
        act = req.action.strip().lower()
        pref_svc = get_user_preference_service()

        if act == "status":
            disabled = await pref_svc.get_disabled_modules(principal.user_id)
            enabled = sorted(list(ALL_KNOWN_MODULES - disabled))
            disabled_list = sorted(list(disabled))

            if not disabled_list:
                spoken = (
                    f"All assistant modules are active: {', '.join(enabled)}. "
                    "You can say 'disable finance' or 'disable health' to turn one off."
                )
            else:
                spoken = (
                    f"Active modules: {', '.join(enabled)}. "
                    f"Disabled modules: {', '.join(disabled_list)}. "
                    "Say 'enable' followed by the module name to turn it back on."
                )

            if len(spoken) > 300:
                spoken = (
                    f"Active: {len(enabled)} modules. Disabled: {', '.join(disabled_list)}. "
                    "Say 'enable' followed by a module name to re-enable it."
                )

            return ok(
                spoken_summary=spoken,
                data={
                    "active_modules": enabled,
                    "disabled_modules": disabled_list,
                },
                next_actions=["what are my settings?", "disable finance"],
                module="settings",
                version="0.1.0",
            )

        if act == "disable_module":
            if not req.module:
                raise InvalidInputError("Please specify which module to disable.")
            mod = req.module.strip().lower()
            if mod not in ALL_KNOWN_MODULES:
                valid = ", ".join(sorted(ALL_KNOWN_MODULES))
                raise InvalidInputError(f"Unknown module '{mod}'. Valid modules: {valid}")

            await pref_svc.set_module_enabled(principal.user_id, mod, False)
            spoken = (
                f"Disabled the {mod} module. You can re-enable it anytime by saying 'enable {mod}'."
            )
            return ok(
                spoken_summary=spoken,
                data={"module": mod, "status": "disabled"},
                next_actions=[f"enable {mod}", "what are my settings?"],
                module="settings",
                version="0.1.0",
            )

        if act == "enable_module":
            if not req.module:
                raise InvalidInputError("Please specify which module to enable.")
            mod = req.module.strip().lower()
            if mod not in ALL_KNOWN_MODULES:
                valid = ", ".join(sorted(ALL_KNOWN_MODULES))
                raise InvalidInputError(f"Unknown module '{mod}'. Valid modules: {valid}")

            await pref_svc.set_module_enabled(principal.user_id, mod, True)
            spoken = f"Enabled the {mod} module."
            return ok(
                spoken_summary=spoken,
                data={"module": mod, "status": "enabled"},
                next_actions=["what are my settings?"],
                module="settings",
                version="0.1.0",
            )

        raise InvalidInputError(
            f"Unknown action '{req.action}'. Valid actions: status, enable_module, disable_module."
        )

    except SahayakError as err:
        return fail(err, module="settings", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in settings tool: %s", exc)
        return fail(SahayakError(), module="settings", version="0.1.0")
