import unittest
from unittest.mock import AsyncMock, MagicMock

import utils
from cogs.admin_panel import AdminPanel, ReplaceConfirmation, ScheduleModal
from cogs.birthday import Birthday
from cogs.quotes import Quotes


class AdminPanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = MagicMock()
        self.cog.settings = {"enabled": True, "hour": 9, "minute": 0, "days": 1}
        self.cog.birthdays = [{"character_id": "1"}]
        self.cog.quotes = []
        self.cog.tz = utils.get_timezone()
        self.cog._change_settings = AsyncMock()
        self.cog._birthday_update = AsyncMock()
        self.interaction = MagicMock()
        self.interaction.user.id = 123
        self.interaction.response = AsyncMock()
        self.interaction.edit_original_response = AsyncMock()
        self.interaction.message.edit = AsyncMock()

    def test_only_four_commands_with_admin_defaults(self):
        commands = Birthday.__cog_app_commands__ + Quotes.__cog_app_commands__
        self.assertEqual({c.name for c in commands}, {"birthday", "birthday_admin", "quote", "quote_admin"})
        for command in commands:
            if command.name.endswith("_admin"):
                self.assertTrue(command.default_permissions.administrator)
                self.assertTrue(command.guild_only)
                self.assertEqual(command.checks, [])

    async def test_commands_open_private_panel_without_update(self):
        for cog_class, feature in [(Birthday, "birthday"), (Quotes, "quote")]:
            file = MagicMock(filename="data.csv")
            command = getattr(cog_class, feature + "_admin")
            await command.callback(self.cog, self.interaction, file)
            kwargs = self.interaction.response.send_message.call_args.kwargs
            self.assertTrue(kwargs["ephemeral"])
            self.assertIs(kwargs["view"].file, file)
        self.cog._birthday_update.assert_not_awaited()

    async def test_owner_and_busy_checks(self):
        panel = AdminPanel(self.cog, "birthday", 123)
        self.assertTrue(panel.replace_data.disabled)
        self.interaction.user.id = 456
        self.assertFalse(await panel.interaction_check(self.interaction))
        self.interaction.user.id = 123
        panel.busy = True
        self.assertFalse(await panel.interaction_check(self.interaction))
        panel.busy = False
        self.assertTrue(await panel.interaction_check(self.interaction))

    async def test_toggle_retains_birthday_reset_semantics(self):
        panel = AdminPanel(self.cog, "birthday", 123)
        self.cog.settings["enabled"] = False
        await panel.toggle.callback(self.interaction)
        self.cog._change_settings.assert_awaited_once_with({"enabled": True, "last_announced_date": None})
        self.assertFalse(panel.busy)

    async def test_schedule_validation_and_save(self):
        panel = AdminPanel(self.cog, "quote", 123)
        modal = ScheduleModal(panel)
        modal.hour._value = "24"
        await modal.on_submit(self.interaction)
        self.cog._change_settings.assert_not_awaited()
        modal.hour._value = "12"
        modal.minute._value = "30"
        modal.days._value = "3"
        await modal.on_submit(self.interaction)
        self.cog._change_settings.assert_awaited_once_with({"hour": 12, "minute": 30, "days": 3, "last_posted_at": None})

    async def test_expired_panel_prevents_modal_save(self):
        panel = AdminPanel(self.cog, "birthday", 123)
        modal = ScheduleModal(panel)
        panel.stop()
        modal.hour._value = "12"
        await modal.on_submit(self.interaction)
        self.cog._change_settings.assert_not_awaited()

    async def test_cancel_and_timeout_do_not_update(self):
        panel = AdminPanel(self.cog, "birthday", 123, MagicMock())
        confirm = ReplaceConfirmation(panel)
        await confirm.cancel.callback(self.interaction)
        self.assertFalse(await confirm.interaction_check(self.interaction))
        panel.stop()
        other = ReplaceConfirmation(panel)
        self.assertFalse(await other.interaction_check(self.interaction))
        self.cog._birthday_update.assert_not_awaited()

    async def test_confirm_updates_once_and_blocks_other_confirmations(self):
        file = MagicMock()
        panel = AdminPanel(self.cog, "birthday", 123, file)
        first, second = ReplaceConfirmation(panel), ReplaceConfirmation(panel)
        self.assertTrue(await first.interaction_check(self.interaction))
        await first.confirm.callback(self.interaction)
        self.cog._birthday_update.assert_awaited_once_with(self.interaction, file)
        self.assertFalse(await first.interaction_check(self.interaction))
        self.assertFalse(await second.interaction_check(self.interaction))
        self.assertFalse(panel.busy)

    async def test_save_failure_does_not_lock_panel(self):
        panel = AdminPanel(self.cog, "birthday", 123)
        self.cog._change_settings.side_effect = OSError("disk failure")
        with self.assertRaises(OSError):
            await panel.toggle.callback(self.interaction)
        self.assertFalse(panel.busy)
        self.interaction.edit_original_response.assert_not_awaited()
