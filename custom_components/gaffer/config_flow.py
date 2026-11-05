"""Single-instance setup with no options and no credentials."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, NAME


class GafferConfigFlow(ConfigFlow, domain=DOMAIN):
    """Confirm setup. The manifest's single_config_entry blocks a second entry."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show a confirmation form, then create the entry."""
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=NAME, data={})
