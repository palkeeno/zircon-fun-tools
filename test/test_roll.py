"""Dice option, ordering, validation, and registration tests."""

import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

from cogs.roll import MAX_COUNT, MAX_SIDES, Roll, setup
from main import FunToolsBot


class TestRoll(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cog = Roll(MagicMock())
        self.interaction = MagicMock()
        self.interaction.response.send_message = AsyncMock()
        self.interaction.response.is_done.return_value = False
        self.interaction.followup.send = AsyncMock()

    async def test_optional_options_and_ordering(self):
        cases = [
            ({}, [4], "4", 6),
            ({"n": 20}, [20], "20", 20),
            ({"n": 20, "m": 3}, [20, 1, 20], "20, 1, 20", 20),
            ({"n": 20, "m": 3, "sort": True}, [20, 1, 20], "1, 20, 20", 20),
            ({"m": 3}, [6, 1, 4], "6, 1, 4", 6),
            ({"m": 3, "sort": True}, [6, 1, 4], "1, 4, 6", 6),
            ({"sort": True}, [3], "3", 6),
            ({"n": 1, "m": 3}, [1, 1, 1], "1, 1, 1", 1),
        ]
        for options, values, expected, sides in cases:
            with self.subTest(options=options):
                self.interaction.response.send_message.reset_mock()
                with patch("cogs.roll.random.randint", side_effect=values) as randint:
                    await Roll.roll.callback(self.cog, self.interaction, **options)
                self.assertEqual(randint.call_args_list, [call(1, sides)] * len(values))
                self.interaction.response.send_message.assert_awaited_once_with(expected)

    async def test_invalid_bounds_do_not_roll(self):
        for options in ({"n": 0}, {"n": -1}, {"n": MAX_SIDES + 1},
                        {"m": 0}, {"m": -1}, {"m": MAX_COUNT + 1}):
            with self.subTest(options=options), patch("cogs.roll.random.randint") as randint:
                self.interaction.response.send_message.reset_mock()
                await Roll.roll.callback(self.cog, self.interaction, **options)
                randint.assert_not_called()
                self.assertTrue(self.interaction.response.send_message.await_args.kwargs["ephemeral"])

    async def test_largest_response_fits_discord(self):
        with patch("cogs.roll.random.randint", return_value=MAX_SIDES):
            await Roll.roll.callback(self.cog, self.interaction, n=MAX_SIDES, m=MAX_COUNT)
        content = self.interaction.response.send_message.await_args.args[0]
        self.assertLessEqual(len(content), 2000)
        self.assertEqual(len(content.split(", ")), MAX_COUNT)

    async def test_failure_reports_private_error(self):
        with patch("cogs.roll.random.randint", side_effect=RuntimeError("failure")), patch("cogs.roll.logger.exception"):
            await Roll.roll.callback(self.cog, self.interaction)
        self.assertTrue(self.interaction.response.send_message.await_args.kwargs["ephemeral"])

    async def test_registration_and_option_metadata(self):
        bot = FunToolsBot()
        self.addAsyncCleanup(bot.close)
        self.assertIn("cogs.roll", bot.initial_extensions)
        await setup(bot)
        command = bot.tree.get_command("roll")
        self.assertIsNotNone(command)
        self.assertEqual([p.name for p in command.parameters], ["n", "m", "sort"])
        self.assertTrue(all(not p.required for p in command.parameters))
        self.assertEqual([p.default for p in command.parameters], [6, 1, False])
        self.assertEqual(command.parameters[0].max_value, MAX_SIDES)
        self.assertEqual(command.parameters[1].max_value, MAX_COUNT)
