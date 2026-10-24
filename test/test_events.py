import test
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import config
from cogs.events import Events, EventView, select_winners


def event(**changes):
    item = dict(id="e", title="test", owner=99, guild=config.GUILD_ID, role=10, required=0,
                channels=[20], condition="message", method="random", count=1, state="open",
                entries={}, options=["A", "B", "C"], keyword="参加", contains=False,
                message_id=30, emoji="✅", question="参加名", interval=5)
    item.update(changes)
    return item


class Selection(unittest.TestCase):
    def test_random_unique(self):
        result = select_winners(event(count=3, entries={str(i): {} for i in range(5)}))
        self.assertEqual(len(set(result)), 3)

    def test_majority_and_ties(self):
        entries = {"1": {"vote": 0}, "2": {"vote": 1}, "3": {"vote": 0}, "4": {"vote": 1}}
        self.assertEqual(set(select_winners(event(method="majority", entries=entries))), set(entries))

    def test_minority_ignores_zero_and_nonvoters(self):
        entries = {"1": {"vote": 0}, "2": {"vote": 0}, "3": {"vote": 1}, "4": {}}
        self.assertEqual(select_winners(event(method="minority", entries=entries)), ["3"])

    def test_no_candidates_does_not_draw(self):
        for mode in ["random", "majority", "minority"]:
            with self.assertRaises(ValueError):
                select_winners(event(method=mode))


class Lifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "events.json")
        self.cog = Events(MagicMock(), self.path)
        self.cog.events = {"e": event()}
        self.member = MagicMock(id=1, bot=False, roles=[])
        self.member.guild.id = config.GUILD_ID
        self.member.add_roles = AsyncMock()
        self.member.remove_roles = AsyncMock()
        self.guild = self.member.guild
        self.guild.fetch_member = AsyncMock(return_value=self.member)
        self.channel = MagicMock(send=AsyncMock())

    async def test_join_idempotent_and_restart(self):
        await self.cog.join("e", self.member, via="message")
        await self.cog.join("e", self.member, via="message")
        loaded = Events(MagicMock(), self.path)
        self.assertEqual(list(loaded.events["e"]["entries"]), ["1"])
        await loaded.cog_load()
        loaded.bot.add_view.assert_called_once()

    async def test_eligibility(self):
        self.cog.events["e"]["required"] = 5
        with self.assertRaises(ValueError):
            await self.cog.join("e", self.member, via="message")
        self.member.roles = [MagicMock(id=5)]
        await self.cog.join("e", self.member, via="message")
        self.member.bot = True
        with self.assertRaises(ValueError):
            await self.cog.join("e", self.member, via="message")

    async def test_owner_and_other_guild_cannot_enter_lottery(self):
        for uid, guild_id in [(99, config.GUILD_ID), (1, config.GUILD_ID + 1)]:
            self.member.id = uid
            self.member.guild.id = guild_id
            with self.assertRaises(ValueError):
                await self.cog.join("e", self.member, via="message")
        self.assertEqual(self.cog.events["e"]["entries"], {})
        self.member.add_roles.assert_not_awaited()

    async def test_wrong_condition_and_late_entry(self):
        with self.assertRaises(ValueError):
            await self.cog.join("e", self.member, via="join")
        self.cog.events["e"]["state"] = "drawing"
        with self.assertRaises(ValueError):
            await self.cog.join("e", self.member, via="message")

    async def test_votes_require_qualification_but_button_can_join(self):
        self.cog.events["e"].update(method="minority")
        with self.assertRaises(ValueError):
            await self.cog.join("e", self.member, via="vote", vote=0)
        self.cog.events["e"]["condition"] = "button"
        await self.cog.join("e", self.member, via="vote", vote=0)
        await self.cog.join("e", self.member, via="vote", vote=1)
        self.assertEqual(self.cog.events["e"]["entries"], {"1": {"vote": 1}})

    async def test_leave_removes_only_participation_role(self):
        await self.cog.join("e", self.member, via="message")
        await self.cog.leave("e", self.member)
        self.member.remove_roles.assert_awaited_once()
        self.assertFalse(self.cog.events["e"]["entries"])

    async def test_failed_role_add_stays_tracked_for_cleanup(self):
        self.member.add_roles.side_effect = discord.Forbidden(MagicMock(status=403), "denied")
        with self.assertRaises(discord.Forbidden):
            await self.cog.join("e", self.member, via="message")
        self.assertIn("1", Events(MagicMock(), self.path).events["e"]["entries"])

    async def test_draw_then_automatic_cleanup(self):
        await self.cog.join("e", self.member, via="message")
        with patch("cogs.events.asyncio.sleep", new=AsyncMock()):
            await self.cog.advance("e", self.guild, self.channel)
        self.assertEqual(self.cog.events, {})
        self.member.remove_roles.assert_awaited_once()
        self.assertEqual(json.loads(Path(self.path).read_text()), {})

    async def test_announcement_failure_reuses_winners(self):
        await self.cog.join("e", self.member, via="message")
        self.channel.send.side_effect = discord.HTTPException(MagicMock(status=500), "failed")
        with self.assertRaises(discord.HTTPException):
            await self.cog.advance("e", self.guild, self.channel)
        restored = Events(MagicMock(), self.path)
        self.assertEqual(restored.events["e"]["winners"], ["1"])
        self.assertEqual(restored.events["e"]["state"], "drawing")

    async def test_cleanup_failure_retry_without_redraw(self):
        await self.cog.join("e", self.member, via="message")
        self.member.remove_roles.side_effect = discord.Forbidden(MagicMock(status=403), "denied")
        await self.cog.advance("e", self.guild, self.channel, reset=True)
        self.assertEqual(self.cog.events["e"]["state"], "cleanup")
        self.member.remove_roles.side_effect = None
        with patch("cogs.events.select_winners", side_effect=AssertionError("redraw")):
            await self.cog.advance("e", self.guild, self.channel)
        self.assertEqual(self.cog.events, {})

    async def test_save_failure_rolls_back(self):
        before = copy.deepcopy(self.cog.events)
        with patch("cogs.events.utils.atomic_write_json", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                await self.cog.join("e", self.member, via="message")
        self.assertEqual(self.cog.events, before)
        self.member.add_roles.assert_not_awaited()

    async def test_message_conditions(self):
        message = MagicMock(guild=self.guild, author=self.member, content="参加", attachments=[])
        message.channel.id = 20
        for condition, matches in [("message", True), ("keyword", True), ("attachment", False), ("button", False)]:
            self.cog.events["e"]["condition"] = condition
            with patch.object(self.cog, "join", new=AsyncMock()) as join:
                await self.cog.on_message(message)
                self.assertEqual(join.await_count, int(matches))

    async def test_reaction_add_and_remove(self):
        self.cog.events["e"]["condition"] = "reaction"
        self.cog.bot.get_guild.return_value = self.guild
        payload = MagicMock(guild_id=config.GUILD_ID, channel_id=20, message_id=30, user_id=1, emoji="✅")
        await self.cog.reaction(payload, False)
        self.assertIn("1", self.cog.events["e"]["entries"])
        await self.cog.reaction(payload, True)
        self.assertFalse(self.cog.events["e"]["entries"])

    async def test_form_persistence_and_view(self):
        self.cog.events["e"]["condition"] = "form"
        await self.cog.join("e", self.member, via="form", answer="ゲーム名")
        self.assertEqual(self.cog.events["e"]["entries"]["1"]["answer"], "ゲーム名")
        self.assertTrue(EventView(self.cog, self.cog.events["e"]).is_persistent())

    async def test_new_commands_serialize(self):
        from main import FunToolsBot
        bot = FunToolsBot()
        try:
            await bot.add_cog(Events(bot, str(Path(self.temp.name) / "new.json")))
            self.assertIn("cogs.events", bot.initial_extensions)
            for command in bot.tree.get_commands():
                self.assertTrue(command.to_dict(bot.tree)["name"])
        finally:
            await bot.close()

    async def test_majority_completes_in_one_step(self):
        self.cog.events["e"].update(method="majority", entries={"1": {"vote": 0}, "2": {"vote": 0}, "3": {"vote": 1}})
        await self.cog.advance("e", self.guild, self.channel)
        self.assertFalse(self.cog.events)
        self.assertEqual(self.guild.fetch_member.await_count, 3)

    async def test_insufficient_entries_keep_reception_open(self):
        with self.assertRaises(ValueError):
            await self.cog.advance("e", self.guild, self.channel)
        self.assertEqual(self.cog.events["e"]["state"], "open")

    async def test_create_public_panel_and_exclusive_role(self):
        item = MagicMock(user=MagicMock(id=99), followup=MagicMock(send=AsyncMock()))
        item.guild.id = config.GUILD_ID
        item.guild.get_channel.return_value = MagicMock(spec=discord.TextChannel)
        async def members(**kwargs):
            if False:
                yield None
        item.guild.fetch_members = members
        role = MagicMock(id=88)
        with patch("cogs.events.validate_role"):
            await self.cog.create(item, title="募集", role=role, required=None, channels="20", condition="button", method="minority", count=1, options="A|B")
            item.followup.send.assert_awaited_once()
            self.assertTrue(item.followup.send.call_args.kwargs["view"].is_persistent())
            with self.assertRaises(ValueError):
                await self.cog.create(item, title="重複", role=role, required=None, channels="20", condition="button", method="random", count=1)
