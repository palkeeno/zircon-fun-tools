"""Reading flows and Discord payloads, without a live Discord connection."""
import test

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from discord.state import ConnectionState
from cogs.help import Help
from cogs.tarot import ChoiceModal, Tarot, TarotView, card_embed
from cogs.tarot_cards import CARDS, POSITIONS
from main import FunToolsBot


def interaction(owner=1):
    item = MagicMock()
    item.user.id = owner
    item.response.send_message = AsyncMock()
    item.response.edit_message = AsyncMock()
    item.response.send_modal = AsyncMock()
    item.response.is_done.return_value = False
    item.original_response = AsyncMock()
    item.followup.send = AsyncMock()
    return item


class CardTests(unittest.TestCase):
    def test_complete_major_arcana_with_both_meanings(self):
        self.assertEqual([c.number for c in CARDS], list(range(22)))
        self.assertEqual(len({c.name for c in CARDS}), 22)
        self.assertEqual(CARDS[8].name, "力")
        self.assertEqual(CARDS[11].name, "正義")
        for card in CARDS:
            self.assertGreaterEqual(len(card.upright), 4)
            self.assertGreaterEqual(len(card.reversed), 4)
            self.assertTrue(card.theme and card.upright_text and card.reversed_text)

    def test_direction_selects_all_matching_keywords(self):
        for reverse in (False, True):
            embed = card_embed(0, reverse, "1枚目")
            self.assertIn("逆位置" if reverse else "正位置", embed.fields[0].name)
            self.assertEqual(embed.fields[0].value, "／".join(CARDS[0].reversed if reverse else CARDS[0].upright))


class ReadingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.panels = []

    async def asyncTearDown(self):
        for panel in self.panels:
            panel.stop()

    def panel(self, spread="one", mode="single", **kwargs):
        panel = TarotView(1, spread, mode, **kwargs)
        self.panels.append(panel)
        return panel

    async def click(self, panel, action, slot=None):
        item = interaction()
        button = next(button for button in panel.children
                      if button.action == action and button.slot == slot)
        await button.callback(item)
        return item

    async def confirm(self, panel, a="外に出る", b="家で過ごす", question="休日は？"):
        item = await self.click(panel, "input")
        modal = item.response.send_modal.call_args.args[0]
        modal.a._value, modal.b._value = a, b
        modal.question._value = question
        await modal.on_submit(interaction())
        return modal

    async def test_one_selects_actual_pre_shuffled_slot(self):
        panel = self.panel(reversed_=False)
        deck = panel.deck
        self.assertEqual(len(panel.children), 23)
        self.assertEqual(len(panel.embeds()), 1)
        await self.click(panel, "pick", 17)
        self.assertEqual(panel.selected, [17])
        self.assertEqual(panel.phase, "done")
        self.assertEqual(panel.children, [])
        self.assertEqual(len(panel.embeds()), 2)
        self.assertIn(CARDS[deck[17][0]].name, panel.embeds()[1].fields[0].name)
        self.assertTrue(all(not reverse for _, reverse in deck))

    async def test_three_single_preserves_cards_and_position_order(self):
        panel = self.panel("three")
        for i, slot in enumerate((21, 3, 12)):
            await self.click(panel, "pick", slot)
            self.assertEqual(len(panel.embeds()), i + 2)
            self.assertIn(POSITIONS["three"][i][0], panel.embeds()[-1].title)
            if i < 2:
                self.assertTrue(next(b for b in panel.children if b.slot == slot).disabled)
        self.assertEqual(panel.selected, [21, 3, 12])
        self.assertEqual(len({panel.deck[s][0] for s in panel.selected}), 3)

    async def test_three_all_hides_until_three_selections(self):
        panel = self.panel("three", "all")
        for slot in (5, 1):
            await self.click(panel, "pick", slot)
            self.assertEqual(len(panel.embeds()), 1)
        await self.click(panel, "pick", 20)
        self.assertEqual(len(panel.embeds()), 4)

    async def test_deck_permutation_and_reverse_enabled(self):
        with patch("cogs.tarot.random.getrandbits", return_value=1):
            panel = self.panel()
        self.assertEqual(sorted(number for number, _ in panel.deck), list(range(22)))
        self.assertTrue(all(reverse for _, reverse in panel.deck))

    async def test_only_owner_can_operate_or_submit(self):
        panel = self.panel()
        item = interaction(2)
        await panel.act(item, "pick", panel.revision, 0)
        self.assertEqual(panel.selected, [])
        item.response.send_message.assert_awaited_once()
        self.assertTrue(item.response.send_message.call_args.kwargs["ephemeral"])
        panel = self.panel("choice")
        modal = ChoiceModal(panel)
        modal.a._value, modal.b._value = "A", "B"
        await modal.on_submit(interaction(2))
        self.assertEqual(panel.phase, "input")

    async def test_double_click_and_parallel_clicks_cannot_advance_twice(self):
        panel = self.panel("three")
        revision = panel.revision
        await asyncio.gather(panel.act(interaction(), "pick", revision, 0),
                             panel.act(interaction(), "pick", revision, 1))
        self.assertEqual(len(panel.selected), 1)
        # Even a new revision cannot pick an already selected slot.
        await panel.act(interaction(), "pick", panel.revision, panel.selected[0])
        self.assertEqual(len(panel.selected), 1)

    async def test_choice_form_confirmation_and_single_flow(self):
        panel = self.panel("choice")
        self.assertIn("公開", panel.embeds()[0].description)
        await self.confirm(panel)
        self.assertEqual(panel.phase, "confirm")
        self.assertEqual(panel.selected, [])
        await self.click(panel, "start")
        self.assertEqual(panel.phase, "reading")
        self.assertEqual(panel.selected, [])
        for i in range(5):
            await self.click(panel, "next")
            self.assertEqual(len(panel.embeds()), i + 2)
            self.assertIn(POSITIONS["choice"][i][0], panel.embeds()[-1].title)
        self.assertEqual(panel.phase, "done")
        self.assertIn("外に出る", panel.embeds()[2].fields[-1].value)
        self.assertIn("家で過ごす", panel.embeds()[3].fields[-1].value)

    async def test_choice_all_and_remaining_all(self):
        for mode in ("single", "all"):
            panel = self.panel("choice", mode)
            await self.confirm(panel)
            await self.click(panel, "start")
            if mode == "single":
                await self.click(panel, "next")
                first = panel.embeds()[1].to_dict()
                await self.click(panel, "all")
                self.assertEqual(panel.embeds()[1].to_dict(), first)
            self.assertEqual(panel.phase, "done")
            self.assertEqual(len(panel.embeds()), 6)
            self.assertEqual(len(set(panel.deck[s][0] for s in panel.selected)), 5)

    async def test_choice_reentry_and_stale_modal(self):
        panel = self.panel("choice")
        old = await self.confirm(panel)
        item = await self.click(panel, "input")
        modal = item.response.send_modal.call_args.args[0]
        self.assertEqual(modal.a.default, "外に出る")
        modal.a._value, modal.b._value = "新A", "新B"
        await modal.on_submit(interaction())
        await old.on_submit(interaction())
        self.assertEqual((panel.a, panel.b), ("新A", "新B"))

    async def test_invalid_choices_do_not_change_state(self):
        panel = self.panel("choice")
        for a, b in ((" ", "B"), ("A", "\n"), ("A", "A")):
            modal = ChoiceModal(panel)
            modal.a._value, modal.b._value = a, b
            with self.assertRaises(ValueError):
                await modal.on_submit(interaction())
            self.assertEqual(panel.phase, "input")
            self.assertEqual(panel.a, "")

    async def test_cancel_keeps_revealed_cards_and_rejects_stale_actions(self):
        panel = self.panel("three")
        await self.click(panel, "pick", 2)
        await self.click(panel, "cancel")
        self.assertEqual(panel.phase, "cancelled")
        self.assertEqual(len(panel.embeds()), 2)
        await panel.act(interaction(), "pick", panel.revision, 1)
        self.assertEqual(panel.selected, [2])

    async def test_timeout_removes_controls_keeps_results_and_invalidates_modal(self):
        panel = self.panel("three")
        panel.message = MagicMock(edit=AsyncMock())
        await self.click(panel, "pick", 0)
        await panel.on_timeout()
        self.assertEqual(panel.phase, "expired")
        self.assertEqual(panel.children, [])
        self.assertEqual(len(panel.embeds()), 2)
        panel.message.edit.assert_awaited_once()
        panel = self.panel("choice")
        modal = ChoiceModal(panel)
        modal.a._value, modal.b._value = "A", "B"
        panel.deadline = time.monotonic() - 1
        await modal.on_submit(interaction())
        self.assertEqual(panel.a, "")

    async def test_interrupted_all_does_not_reveal_partial_results(self):
        panel = self.panel("three", "all")
        await self.click(panel, "pick", 2)
        await panel.on_timeout()
        self.assertEqual(len(panel.embeds()), 1)

    async def test_failed_draw_update_can_retry_same_slot_without_changing_deck(self):
        panel = self.panel()
        deck, revision = panel.deck, panel.revision
        item = interaction()
        item.response.edit_message.side_effect = RuntimeError("Discord update rejected")
        with self.assertRaises(RuntimeError):
            await panel.act(item, "pick", revision, 17)
        self.assertEqual(panel.selected, [])
        self.assertEqual(panel.phase, "reading")
        self.assertEqual(panel.revision, revision)
        self.assertFalse(panel.is_finished())
        await self.click(panel, "pick", 17)
        self.assertEqual(panel.selected, [17])
        self.assertEqual(panel.deck, deck)

    async def test_failed_modal_update_keeps_original_input_and_allows_resubmit(self):
        panel = self.panel("choice")
        modal = ChoiceModal(panel)
        modal.a._value, modal.b._value = "A", "B"
        item = interaction()
        item.response.edit_message.side_effect = RuntimeError("Discord update rejected")
        with self.assertRaises(RuntimeError):
            await modal.on_submit(item)
        self.assertEqual((panel.a, panel.b, panel.phase), ("", "", "input"))
        await modal.on_submit(interaction())
        self.assertEqual((panel.a, panel.b, panel.phase), ("A", "B", "confirm"))

    async def test_discord_store_releases_previous_generations_and_finished_views(self):
        # Exercise the real library store: rebuilding children otherwise leaks
        # old custom-ID handlers, retaining questions/results after completion.
        state = ConnectionState(dispatch=MagicMock(), handlers={}, hooks={}, http=MagicMock())
        panel = self.panel("three")
        state.store_view(panel, 123)
        for slot in (0, 1, 2):
            item = interaction()
            item._state = state
            item.message.id = 123

            async def deliver(**kwargs):
                if kwargs["view"].children:
                    state.store_view(kwargs["view"], 123)

            item.response.edit_message.side_effect = deliver
            await panel.act(item, "pick", panel.revision, slot)
            self.assertLessEqual(len(state._view_store._views.get(123, {})), 23)
        self.assertNotIn(123, state._view_store._views)
        panel = self.panel("one")
        state.store_view(panel, 456)
        await panel.on_timeout()
        self.assertNotIn(456, state._view_store._views)

    async def test_failed_update_restores_real_discord_dispatch_registration(self):
        state = ConnectionState(dispatch=MagicMock(), handlers={}, hooks={}, http=MagicMock())
        panel = self.panel()
        state.store_view(panel, 123)
        item = interaction()
        item._state = state
        item.message.id = 123
        item.response.edit_message.side_effect = RuntimeError("Discord update rejected")
        with self.assertRaises(RuntimeError):
            await panel.act(item, "pick", panel.revision, 0)
        self.assertEqual(len(state._view_store._views[123]), 23)
        self.assertEqual(panel.selected, [])

    async def test_payload_limits_with_maximum_input_and_markdown(self):
        panel = self.panel("choice", "all", private=True)
        await self.confirm(panel, a="*" * 80, b="@" * 80, question="_" * 200)
        self.assertIn("自分だけ", panel.embeds()[0].description)
        await self.click(panel, "start")
        self.assertLessEqual(sum(len(e) for e in panel.embeds()), 6000)
        for embed in panel.embeds():
            self.assertLessEqual(len(embed.title), 256)
            self.assertLessEqual(len(embed.description or ""), 4096)
            for field in embed.fields:
                self.assertLessEqual(len(field.value), 1024)
        self.assertIn("\\*", panel.embeds()[0].description)


class TarotCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_commands_public_private_and_independent_options(self):
        cog = Tarot()
        for command in (Tarot.one, Tarot.three, Tarot.choice):
            for private in (False, True):
                item = interaction()
                await command.callback(cog, item, private=private, reversed=False)
                kwargs = item.response.send_message.call_args.kwargs
                self.assertEqual(kwargs["ephemeral"], private)
                panel = kwargs["view"]
                self.assertIs(panel.message, item.original_response.return_value)
                self.assertEqual(panel.mode, "single")
                self.assertTrue(all(not reverse for _, reverse in panel.deck))
                panel.stop()

    async def test_dictionary_has_every_card_and_both_directions(self):
        for number in range(22):
            item = interaction()
            await Tarot.card.callback(Tarot(), item, number, private=True)
            kwargs = item.response.send_message.call_args.kwargs
            self.assertTrue(kwargs["ephemeral"])
            self.assertIn(CARDS[number].name, kwargs["embed"].title)
            self.assertEqual([f.name for f in kwargs["embed"].fields], ["正位置", "逆位置"])

    async def test_registration_choices_and_help_for_groups(self):
        bot = FunToolsBot()
        async with bot:
            await bot.load_extension("cogs.tarot")
            await bot.add_cog(Help(bot))
            self.assertIn("cogs.tarot", bot.initial_extensions)
            group = bot.tree.get_command("tarot")
            self.assertEqual({c.name for c in group.commands}, {"one", "three", "choice", "card"})
            for name in ("three", "choice"):
                mode = next(p for p in group.get_command(name).parameters if p.name == "mode")
                self.assertEqual([c.value for c in mode.choices], ["single", "all"])
            self.assertEqual(len(group.get_command("card").parameters[0].choices), 22)
            item = interaction()
            await Help.help_command.callback(bot.get_cog("Help"), item)
            kwargs = item.response.send_message.call_args.kwargs
            names = [f.name for f in kwargs["embed"].fields]
            self.assertIn("/tarot one", names)
            self.assertIn("/tarot three", names)
            kwargs["view"].stop()

    async def test_callback_and_modal_errors_use_private_shared_response(self):
        panel = TarotView(1, "choice")
        item = interaction()
        await panel.on_error(item, ValueError("入力を確認してください。"), None)
        self.assertTrue(item.response.send_message.call_args.kwargs["ephemeral"])
        modal = ChoiceModal(panel)
        item = interaction()
        await modal.on_error(item, ValueError("入力を確認してください。"))
        self.assertTrue(item.response.send_message.call_args.kwargs["ephemeral"])
        panel.stop()
