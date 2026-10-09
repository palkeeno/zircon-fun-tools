import test
import asyncio
import datetime
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from PIL import Image

import config
import utils
from birthday_records import normalize as birthday_normalize, select
from quote_records import normalize, merge_records, parse_upload
from cogs.birthday import Birthday
from cogs.quotes import Quotes
from cogs.pagination import Pagination
from cogs.poster import Poster
from cogs.help import Help
from cogs.role_tools import RoleTools, RemovalConfirmation, validate_role
from cogs.lottery import Lottery
from command_errors import send_error
from main import FunToolsBot
from poster_cache import PosterCache
import setup_fonts


def interaction():
    item = MagicMock()
    item.user.id = 99
    item.response = AsyncMock()
    item.response.is_done = MagicMock(return_value=False)
    item.followup = AsyncMock()
    item.original_response = AsyncMock()
    item.edit_original_response = AsyncMock()
    return item


class QuoteValidationTests(unittest.TestCase):
    def test_missing_blank_wrong_type_and_limits(self):
        for row in [None, [], {}, {"speaker": " ", "text": "x"}, {"speaker": "A", "text": None},
                    {"speaker": 1, "text": "x"}, {"speaker": "A", "text": "x" * 4001},
                    {"speaker": "A", "text": "x", "character_id": "../x"},
                    {"speaker": "A", "text": "x", "created_at": "invalid"}]:
            with self.subTest(row=str(row)[:80]), self.assertRaises(ValueError):
                normalize(row)

    def test_identity_and_creation_history_survive_import_and_edit(self):
        old = dict(id="stable", speaker="A", text="original", character_id="1",
                   created_by=42, created_at="2020-01-01T00:00:00+09:00", updated_at="2020-01-02T00:00:00+09:00")
        now = "2026-10-09T00:00:00+09:00"
        unchanged = merge_records([dict(speaker=" A ", text="original", character_id="1")], [old], 99, now)[0]
        self.assertEqual(unchanged, old)
        edited = merge_records([{**old, "text": "edited", "created_by": 123}], [old], 99, now)[0]
        self.assertEqual(edited["id"], "stable")
        self.assertEqual(edited["created_by"], 42)
        self.assertEqual(edited["created_at"], old["created_at"])
        self.assertEqual(edited["updated_at"], now)

    def test_duplicate_ids_and_ambiguous_contents_rejected(self):
        row = dict(id="same", speaker="A", text="text")
        with self.assertRaises(ValueError):
            merge_records([row, row], [], 99, "2026-10-09T00:00:00")
        existing = [{**row, "id": "1", "character_id": None}, {**row, "id": "2", "character_id": None}]
        with self.assertRaises(ValueError):
            merge_records([dict(speaker="A", text="text")], existing, 99, "2026-10-09T00:00:00")

    def test_csv_bom_quoted_multiline_and_export_json_round_trip(self):
        content = '\ufeffid,speaker,text,character_id,created_by,created_at\nsame,A,"first\nsecond",123,42,2020-01-01T00:00:00\n'.encode('utf-8')
        row = normalize(parse_upload(content, "quotes.csv")[0])
        self.assertEqual(row["id"], "same")
        self.assertEqual(row["text"], "first\nsecond")
        self.assertEqual(row["created_by"], 42)
        self.assertEqual(parse_upload(json.dumps({"quotes": [row]}).encode(), "quotes.json"), [row])
        with self.assertRaises(ValueError):
            parse_upload(b"speaker,text\nA,text,extra", "x.csv")


class QuoteCommandsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cog = Quotes(MagicMock(), str(Path(self.directory.name) / 'quotes.json'))
        self.item = interaction()

    async def asyncTearDown(self):
        self.directory.cleanup()

    async def test_add_edit_clear_delete_confirmation_and_disk_reload(self):
        await Quotes.quote_add.callback(self.cog, self.item, 'A', 'original', '123')
        old = dict(self.cog.quotes[0])
        await Quotes.quote_edit.callback(self.cog, self.item, old['id'], text='edited', clear_character=True)
        self.assertEqual(self.cog.quotes[0]['created_at'], old['created_at'])
        self.assertEqual(self.cog.quotes[0]['created_by'], 99)
        self.assertIsNone(self.cog.quotes[0]['character_id'])
        reloaded = Quotes(MagicMock(), self.cog.data_path)
        self.assertEqual(reloaded.quotes, self.cog.quotes)
        await Quotes.quote_delete.callback(self.cog, self.item, old['id'])
        self.assertEqual(len(self.cog.quotes), 1)
        await Quotes.quote_delete.callback(self.cog, self.item, old['id'], confirm=True)
        self.assertEqual(self.cog.quotes, [])
        self.assertEqual(json.loads(Path(self.cog.data_path).read_text())['quotes'], [])

    async def test_invalid_bulk_update_preserves_memory_and_disk(self):
        await Quotes.quote_add.callback(self.cog, self.item, 'A', 'original')
        previous, content = list(self.cog.quotes), Path(self.cog.data_path).read_bytes()
        upload = MagicMock(filename='quotes.json', size=100)
        upload.read = AsyncMock(return_value=b'[{"speaker":"A","text":"valid"},{"speaker":"","text":"bad"}]')
        await Quotes.quote_update.callback(self.cog, self.item, upload)
        self.assertEqual(self.cog.quotes, previous)
        self.assertEqual(Path(self.cog.data_path).read_bytes(), content)

    async def test_id_and_character_search_and_pagination(self):
        self.cog.quotes = [dict(id=f'id-{i}', speaker='A', text=f'text-{i}', character_id='123') for i in range(12)]
        await self.cog._handle_search(self.item, 'id-11')
        self.assertIn('id-11', self.item.response.send_message.call_args.kwargs['embed'].fields[0].name)
        await self.cog._handle_search(self.item, '123')
        view = self.item.response.send_message.call_args.kwargs['view']
        names = []
        for _ in range(3):
            names.extend(field.name for field in view.embed().fields)
            await view.next.callback(self.item)
        self.assertEqual(len(set(names)), 12)
        await view.previous.callback(self.item)
        self.assertEqual(view.page, 1)
        stranger = interaction()
        stranger.user.id = 1
        self.assertFalse(await view.interaction_check(stranger))
        await view.on_timeout()
        self.assertTrue(all(child.disabled for child in view.children))

    async def test_read_validation_reports_rejected_and_preserves_original(self):
        path = Path(self.cog.data_path)
        payload = [{'id': 'valid', 'speaker': 'A', 'text': 'ok'}, {'speaker': '', 'text': 'bad'}, 4]
        path.write_text(json.dumps(payload))
        original = path.read_bytes()
        self.cog._load_data()
        self.assertEqual([q['id'] for q in self.cog.quotes], ['valid'])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(json.loads(Path(str(path) + '.rejected.json').read_text(encoding='utf-8'))), 2)

    async def test_legacy_identity_stable_even_with_rejected_rows(self):
        path = Path(self.cog.data_path)
        path.write_text('[{"speaker":"A","text":"ok"},null]')
        self.cog._load_data()
        identity = self.cog.quotes[0]['id']
        self.cog._load_data()
        self.assertEqual(self.cog.quotes[0]['id'], identity)

    async def test_removing_rejected_rows_does_not_change_legacy_identities(self):
        path = Path(self.cog.data_path)
        rows = [None, dict(speaker='A', text='same'), {'speaker': ''},
                dict(speaker='B', text='other'), dict(speaker='A', text='same')]
        path.write_text(json.dumps(rows))
        self.cog._load_data()
        identities = [q['id'] for q in self.cog.quotes]
        self.assertEqual(len(set(identities)), 3)
        repaired = [row for row in rows if isinstance(row, dict) and row.get('text')]
        path.write_text(json.dumps(repaired))
        self.cog._load_data()
        self.assertEqual([q['id'] for q in self.cog.quotes], identities)
        self.cog._load_data()
        self.assertEqual([q['id'] for q in self.cog.quotes], identities)

    async def test_rejected_rows_block_crud_until_explicit_validated_replacement(self):
        path = Path(self.cog.data_path)
        path.write_text('[{"id":"valid","speaker":"A","text":"ok"},null]')
        original = path.read_bytes()
        self.cog._load_data()
        await Quotes.quote_add.callback(self.cog, self.item, 'B', 'new')
        await Quotes.quote_edit.callback(self.cog, self.item, 'valid', text='changed')
        with self.assertRaises(ValueError):
            await Quotes.quote_delete.callback(self.cog, self.item, 'valid', confirm=True)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(self.cog.quotes), 1)
        upload = MagicMock(filename='quotes.json', size=60)
        upload.read = AsyncMock(return_value=b'[{"id":"valid","speaker":"A","text":"repaired"}]')
        await Quotes.quote_update.callback(self.cog, self.item, upload)
        self.assertFalse(self.cog._has_rejected_rows)
        await Quotes.quote_add.callback(self.cog, self.item, 'B', 'new')
        self.assertEqual(len(self.cog.quotes), 2)

    async def test_failed_full_replacement_keeps_rejected_guard(self):
        self.cog._has_rejected_rows = True
        original = self.cog.quotes
        with patch.object(self.cog, '_save_data', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                await self.cog._replace_records([dict(speaker='A', text='ok')], full_replace=True)
        self.assertTrue(self.cog._has_rejected_rows)
        self.assertIs(self.cog.quotes, original)

    async def test_missing_legacy_ids_migrated_once_and_malformed_file_preserved(self):
        path = Path(self.cog.data_path)
        path.write_text('[{"speaker":"A","text":"ok"}]')
        self.cog._load_data()
        identity = self.cog.quotes[0]['id']
        self.cog._load_data()
        self.assertEqual(self.cog.quotes[0]['id'], identity)
        path.write_text('invalid')
        with self.assertRaises(json.JSONDecodeError):
            self.cog._load_data()
        self.assertEqual(path.read_text(), 'invalid')


class BirthdayFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_crud_with_multiple_preserved_legacy_duplicate_groups(self):
        for operation in ('add', 'edit', 'delete'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'birthdays.json'
                cog = Birthday(MagicMock(), str(path))
                rows = [dict(character_id=cid, name=cid, month=10, day=9, reported=reported)
                        for cid in ('A', 'B') for reported in (False, True)]
                path.write_text(json.dumps(rows))
                cog.load_birthdays()
                self.assertEqual(len(cog.birthdays), 4)
                item = interaction()
                if operation == 'add':
                    await Birthday.birthday_add.callback(cog, item, 'C', 'New', 10, 10)
                    self.assertEqual(len(cog.birthdays), 3)
                elif operation == 'edit':
                    await Birthday.birthday_edit.callback(cog, item, 'A', name='Edited')
                    self.assertEqual(len(cog.birthdays), 2)
                    self.assertTrue(next(b for b in cog.birthdays if b['character_id'] == 'A')['reported'])
                else:
                    await Birthday.birthday_delete.callback(cog, item, 'A', confirm=True)
                    self.assertEqual(len(cog.birthdays), 1)
                retained = next(b for b in cog.birthdays if b['character_id'] == 'B')
                self.assertTrue(retained['reported'])
                self.assertEqual(len({b['character_id'] for b in cog.birthdays}), len(cog.birthdays))
                self.assertEqual(json.loads(Path(str(path) + '.bak').read_text()), rows)
                with self.assertRaises(ValueError):
                    await Birthday.birthday_add.callback(cog, item, 'B', 'Duplicate', 10, 9)

    async def test_read_rejects_conflicting_dates_but_keeps_legacy_same_day_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'birthdays.json'
            cog = Birthday(MagicMock(), str(path))
            row = dict(character_id='123', name='A', month=10, day=9)
            path.write_text(json.dumps([row, row]))
            cog.load_birthdays()
            self.assertEqual(len(cog.birthdays), 2)
            path.write_text(json.dumps([row, {**row, 'day': 10}]))
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                cog.load_birthdays()
            self.assertEqual(path.read_bytes(), original)

    async def test_duplicate_character_with_different_date_rejected_by_add_and_import(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'birthdays.json'
            cog = Birthday(MagicMock(), str(path))
            item = interaction()
            await Birthday.birthday_add.callback(cog, item, '123', 'A', 10, 9)
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                await Birthday.birthday_add.callback(cog, item, '123', 'A', 10, 10)
            self.assertEqual(path.read_bytes(), original)
            upload = MagicMock(filename='birthdays.json')
            upload.read = AsyncMock(return_value=b'[{"character_id":"123","name":"A","month":10,"day":9},{"character_id":"123","name":"A","month":10,"day":10}]')
            await Birthday.birthday_update.callback(cog, item, upload)
            self.assertEqual(path.read_bytes(), original)
            self.assertIn('重複', item.followup.send.call_args.args[0])

    async def test_added_today_after_completion_is_announced_without_reposting_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            cog = Birthday(MagicMock(), str(Path(directory) / 'birthdays.json'))
            now = datetime.datetime(2026, 10, 9, 10, 0, tzinfo=cog.tz)
            cog.settings = dict(hour=9, enabled=True, last_announced_date='2026-10-09', last_reset_date='2026-10-09')
            cog.birthdays = [dict(character_id='old', name='Old', month=10, day=9, reported=True)]
            cog._announce_zircon_birthday = AsyncMock(return_value=True)
            await Birthday.birthday_add.callback(cog, interaction(), 'new', 'New', 10, 9)
            with patch('cogs.birthday.datetime.datetime') as clock, patch('config.get_birthday_channel_id', return_value=123):
                clock.now.return_value = now
                await Birthday.birthday_task.coro(cog)
                await Birthday.birthday_task.coro(cog)
            cog._announce_zircon_birthday.assert_awaited_once()
            self.assertEqual(cog._announce_zircon_birthday.call_args.args[1]['character_id'], 'new')
            self.assertTrue(all(b['reported'] for b in cog.birthdays))

    async def test_bulk_import_preserves_sent_flags_and_reopens_pending_today(self):
        with tempfile.TemporaryDirectory() as directory:
            cog = Birthday(MagicMock(), str(Path(directory) / 'birthdays.json'))
            now = datetime.datetime(2026, 10, 9, 10, 0, tzinfo=cog.tz)
            cog.settings = dict(hour=9, enabled=True, last_announced_date='2026-10-09', last_reset_date='2026-10-09')
            cog.birthdays = [dict(character_id='old', name='Old', month=10, day=9, reported=True)]
            item = interaction()
            upload = MagicMock(filename='birthdays.json')
            upload.read = AsyncMock(return_value=b'[{"character_id":"old","name":"Old","month":10,"day":9},{"character_id":"new","name":"New","month":10,"day":9}]')
            await Birthday.birthday_update.callback(cog, item, upload)
            self.assertTrue(cog.birthdays[0]['reported'])
            cog._announce_zircon_birthday = AsyncMock(return_value=True)
            with patch('cogs.birthday.datetime.datetime') as clock, patch('config.get_birthday_channel_id', return_value=123):
                clock.now.return_value = now
                await Birthday.birthday_task.coro(cog)
            self.assertEqual(cog._announce_zircon_birthday.call_args.args[1]['character_id'], 'new')
            cog._announce_zircon_birthday.assert_awaited_once()

    async def test_edit_legacy_same_day_duplicates_collapses_one_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            cog = Birthday(MagicMock(), str(Path(directory) / 'birthdays.json'))
            row = dict(character_id='123', name='A', month=10, day=9, reported=True)
            cog.birthdays = [row, dict(row)]
            await Birthday.birthday_edit.callback(cog, interaction(), '123', name='B')
            self.assertEqual(len(cog.birthdays), 1)
            self.assertEqual(cog.birthdays[0]['name'], 'B')

    async def test_actual_command_filters_and_pages_records(self):
        with tempfile.TemporaryDirectory() as directory:
            cog = Birthday(MagicMock(), str(Path(directory) / 'birthdays.json'))
            cog.birthdays = [dict(character_id=str(i), name='A', month=10, day=9) for i in range(7)]
            item = interaction()
            now = datetime.datetime(2026, 10, 9, tzinfo=cog.tz)
            with patch('cogs.birthday.datetime.datetime') as clock:
                clock.now.return_value = now
                await Birthday.birthday.callback(cog, item, mode='today')
            view = item.response.send_message.call_args.kwargs['view']
            self.assertEqual(len(view.records), 7)
            await view.next.callback(item)
            self.assertEqual(len(view.embed().fields), 2)

    def test_today_month_upcoming_year_boundary_and_leap_day(self):
        rows = [dict(character_id=str(i), name='A', month=m, day=d) for i, (m, d) in enumerate([(12, 31), (1, 1), (2, 29), (12, 1)])]
        today = datetime.date(2026, 12, 31)
        self.assertEqual(len(select(rows, 'today', today)), 1)
        self.assertEqual(len(select(rows, 'month', today)), 2)
        # Leap birthday occurs in 2028, after the next Dec 1 birthday.
        self.assertEqual([b['character_id'] for b in select(rows, 'upcoming', today)], ['0', '1', '3', '2'])
        with self.assertRaises(ValueError):
            birthday_normalize(dict(character_id='1', name='A', month=2, day=31))

    async def test_image_failure_sends_text_and_marks_reported_only_after_send(self):
        with tempfile.TemporaryDirectory() as directory:
            cog = Birthday(MagicMock(), str(Path(directory) / 'birthdays.json'))
            cog.birthdays = [dict(character_id='1', name='A', month=10, day=9, reported=False)]
            channel = MagicMock(send=AsyncMock())
            cog.bot.get_channel.return_value = channel
            with patch.object(config.IMAGE_CACHE, 'get', new=AsyncMock(side_effect=OSError('offline'))), patch('config.get_birthday_channel_id', return_value=123):
                self.assertTrue(await cog._announce_today_birthdays(datetime.datetime(2026, 10, 9)))
            self.assertTrue(cog.birthdays[0]['reported'])
            self.assertNotIn('file', channel.send.call_args.kwargs)
            self.assertIn('A', channel.send.call_args.kwargs['embed'].description)

    async def test_crud_and_invalid_read_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'birthdays.json'
            cog = Birthday(MagicMock(), str(path))
            item = interaction()
            await Birthday.birthday_add.callback(cog, item, '123', 'A', 2, 29)
            await Birthday.birthday_edit.callback(cog, item, '123', name='B', month=3, day=1)
            self.assertEqual(cog.birthdays[0]['name'], 'B')
            await Birthday.birthday_delete.callback(cog, item, '123')
            self.assertEqual(len(cog.birthdays), 1)
            await Birthday.birthday_delete.callback(cog, item, '123', confirm=True)
            self.assertEqual(cog.birthdays, [])
            path.write_text('[null,{"character_id":"1","month":2,"day":31}]')
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                cog.load_birthdays()
            self.assertEqual(path.read_bytes(), original)
            self.assertTrue(Path(str(path) + '.rejected.json').exists())


class RoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_fetches_all_members_and_requires_confirmation(self):
        guild, role, actor = self.fixtures()
        async def fetch(**kwargs):
            self.assertIsNone(kwargs['limit'])
            yield MagicMock(roles=[role])
        guild.fetch_members.side_effect = fetch
        item = interaction()
        item.guild, item.user = guild, actor
        await RoleTools.remove_role.callback(RoleTools(MagicMock()), item, role)
        self.assertIn('1人', item.followup.send.call_args.args[0])
        self.assertIsInstance(item.followup.send.call_args.kwargs['view'], RemovalConfirmation)
        role.delete.assert_not_called()

    def fixtures(self):
        guild, role, actor = MagicMock(), MagicMock(), MagicMock()
        guild.id = 1
        guild.owner_id = 99
        actor.id = 99
        actor.guild_permissions.manage_roles = True
        guild.me.guild_permissions.manage_roles = True
        role.id = 2
        role.name = 'Members'
        role.is_default.return_value = False
        role.managed = False
        role.__ge__.return_value = False
        guild.get_role.return_value = role
        return guild, role, actor

    def test_permissions_hierarchy_and_managed_roles(self):
        guild, role, actor = self.fixtures()
        validate_role(guild, actor, role)
        for change in ['everyone', 'managed', 'bot_permission', 'actor_permission', 'hierarchy']:
            guild, role, actor = self.fixtures()
            if change == 'everyone': role.is_default.return_value = True
            if change == 'managed': role.managed = True
            if change == 'bot_permission': guild.me.guild_permissions.manage_roles = False
            if change == 'actor_permission': actor.guild_permissions.manage_roles = False
            if change == 'hierarchy': role.__ge__.return_value = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_role(guild, actor, role)

    async def test_all_members_including_bots_partial_failure_role_not_deleted(self):
        guild, role, actor = self.fixtures()
        members = [MagicMock(id=i, roles=[role], remove_roles=AsyncMock()) for i in range(3)]
        members[0].bot = True
        members[1].remove_roles.side_effect = discord.Forbidden(MagicMock(status=403), 'denied')
        async def fetch(**kwargs):
            for member in members:
                yield member
        guild.fetch_members.side_effect = fetch
        cog = RoleTools(MagicMock())
        view = RemovalConfirmation(cog, 99, guild, role)
        item = interaction()
        item.user = actor
        await view.confirm.callback(item)
        for member in members:
            member.remove_roles.assert_awaited_once_with(role, reason='/remove-role by 99', atomic=True)
        role.delete.assert_not_called()
        self.assertIn('成功2人・失敗1人', item.edit_original_response.call_args.kwargs['content'])
        self.assertEqual(cog.running, set())
        self.assertFalse(await view.interaction_check(item))

    async def test_cancel_and_non_owner_do_not_change_roles(self):
        guild, role, actor = self.fixtures()
        view = RemovalConfirmation(RoleTools(MagicMock()), 99, guild, role)
        item = interaction()
        item.user.id = 1
        self.assertFalse(await view.interaction_check(item))
        item.user.id = 99
        await view.cancel.callback(item)
        guild.fetch_members.assert_not_called()
        role.delete.assert_not_called()


class PosterQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_failing_thread_during_shutdown_does_not_restart_worker_loop(self):
        entered, release = threading.Event(), threading.Event()
        def render(cid):
            entered.set()
            release.wait(2)
            raise OSError('thread failed during shutdown')
        with patch.object(self.cog, '_render_poster', side_effect=render):
            caller = asyncio.create_task(Poster.poster.callback(self.cog, interaction(), '123'))
            while not entered.is_set(): await asyncio.sleep(0.001)
            stopping = asyncio.create_task(self.cog.cog_unload())
            await asyncio.sleep(0.01)
            release.set()
            await asyncio.wait_for(stopping, timeout=1)
            await asyncio.gather(caller, return_exceptions=True)
        self.assertTrue(all(worker.done() for worker in self.cog._workers))
        self.assertEqual(self.cog._inflight, {})

    async def test_configured_concurrency_and_shutdown_wait_for_threads(self):
        active, peak = 0, 0
        ready, release = threading.Event(), threading.Event()
        mutex = threading.Lock()
        def render(cid):
            nonlocal active, peak
            with mutex:
                active += 1
                peak = max(peak, active)
                if active == 2: ready.set()
            release.wait(2)
            with mutex: active -= 1
            return cid.encode()
        with patch.object(config, 'POSTER_CONCURRENCY', 2), patch.object(self.cog, '_render_poster', side_effect=render):
            callers = [asyncio.create_task(Poster.poster.callback(self.cog, interaction(), str(i))) for i in range(3)]
            while not ready.is_set(): await asyncio.sleep(0.001)
            stopping = asyncio.create_task(self.cog.cog_unload())
            await asyncio.sleep(0.01)
            self.assertFalse(stopping.done())
            release.set()
            await stopping
            await asyncio.gather(*callers, return_exceptions=True)
        self.assertEqual(peak, 2)
        self.assertEqual(active, 0)
        self.assertEqual(self.cog._inflight, {})

    async def asyncSetUp(self):
        self.cog = Poster(MagicMock())

    async def asyncTearDown(self):
        await self.cog.cog_unload()

    async def test_fifo_limit_duplicate_coalescing_and_loop_responsiveness(self):
        entered, release = threading.Event(), threading.Event()
        order = []
        def render(cid):
            order.append(cid)
            entered.set()
            release.wait(2)
            return cid.encode()
        with patch.object(self.cog, '_render_poster', side_effect=render):
            first = asyncio.create_task(Poster.poster.callback(self.cog, interaction(), '1'))
            while not entered.is_set(): await asyncio.sleep(0.001)
            duplicate = asyncio.create_task(Poster.poster.callback(self.cog, interaction(), '1'))
            second = asyncio.create_task(Poster.poster.callback(self.cog, interaction(), '2'))
            await asyncio.sleep(0.01)
            self.assertEqual(order, ['1'])
            self.assertEqual(self.cog._queue.qsize(), 1)
            release.set()
            await asyncio.gather(first, duplicate, second)
        self.assertEqual(order, ['1', '2'])

    async def test_queue_full_rejects_without_starting_generation(self):
        self.cog._queue = asyncio.Queue(maxsize=1)
        future = asyncio.get_running_loop().create_future()
        self.cog._queue.put_nowait(('1', future))
        item = interaction()
        await Poster.poster.callback(self.cog, item, '2')
        self.assertIn('上限', item.response.send_message.call_args.args[0])
        self.assertEqual(self.cog._workers, [])

    async def test_failed_job_does_not_stop_next_job(self):
        with patch.object(self.cog, '_render_poster', side_effect=[OSError('fail'), b'ok']):
            items = [interaction(), interaction()]
            await asyncio.gather(*(Poster.poster.callback(self.cog, item, str(i)) for i, item in enumerate(items)))
        self.assertEqual(self.cog._inflight, {})
        self.assertIn('file', items[1].followup.send.call_args.kwargs)


class CacheFeatureTests(unittest.TestCase):
    def test_scraper_version_change_refreshes_persistent_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.png'
            Image.new('RGB', (8, 8)).save(source)
            with patch.object(config, '_DATA_DIR', directory), patch('setup_fonts.find_japanese_font', return_value=None), \
                 patch.object(config.IMAGE_CACHE, 'get_sync', return_value=source), \
                 patch.object(Poster, '_scrape_character_info', side_effect=[{'name': 'Old'}, {'name': 'New', 'goal': 'new field'}]) as scrape, \
                 patch.object(Poster, '_draw_poster', side_effect=lambda char, mask, info: Image.new('RGB', (1600, 2100), 'red' if info['name'] == 'Old' else 'green')) as draw:
                with patch('cogs.poster.SCRAPER_VERSION', 'old-scraper'):
                    old = Poster(MagicMock())._render_poster('123')
                with patch('cogs.poster.SCRAPER_VERSION', 'new-scraper'):
                    updated = Poster(MagicMock())._render_poster('123')
                    restarted = Poster(MagicMock())._render_poster('123')
                self.assertEqual(scrape.call_count, 2)
                self.assertEqual(draw.call_count, 2)
                self.assertNotEqual(old, updated)
                self.assertEqual(updated, restarted)

    def test_font_replacement_reloads_objects_and_stores_correct_new_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font = root / 'prepared.ttf'
            font.write_bytes(b'old font')
            source = root / 'source.png'
            Image.new('RGB', (8, 8)).save(source)
            old_font, new_font = object(), object()
            with patch.object(config, '_DATA_DIR', directory), patch('setup_fonts.find_japanese_font', return_value=str(font)), \
                 patch.object(config.IMAGE_CACHE, 'get_sync', return_value=source), \
                 patch.object(Poster, '_scrape_character_info', return_value={'name': 'A'}), \
                 patch('cogs.poster.ImageFont.truetype', side_effect=[old_font, new_font]) as loader:
                cog = Poster(MagicMock())
                self.assertIs(cog._try_load_font(config.POSTER_FONT_A, 24), old_font)
                self.assertIs(cog._try_load_font(config.POSTER_FONT_A, 24), old_font)
                loader.assert_called_once()
                def draw(char, mask, info):
                    current = cog._try_load_font(config.POSTER_FONT_A, 24)
                    return Image.new('RGB', (1600, 2100), 'red' if current is old_font else 'green')
                with patch.object(cog, '_draw_poster', side_effect=draw) as painter:
                    original = cog._render_poster('123')
                    font.write_bytes(b'new replacement font')
                    fresh = cog._render_poster('123')
                    self.assertEqual(loader.call_count, 2)
                    self.assertEqual(painter.call_count, 2)
                    self.assertNotEqual(original, fresh)
                    self.assertIs(cog._try_load_font(config.POSTER_FONT_A, 24), new_font)
                    restarted = Poster(MagicMock())
                    self.assertEqual(restarted._render_poster('123'), fresh)
                with Image.open(io.BytesIO(fresh)) as image:
                    self.assertEqual(image.getpixel((0, 0)), (0, 128, 0))

    def test_expired_metadata_refreshes_before_reusing_newer_completed_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / 'assets'
            assets.mkdir()
            source = root / 'source.png'
            Image.new('RGB', (8, 8)).save(source)
            with patch.object(config, '_DATA_DIR', directory), patch('setup_fonts.find_japanese_font', return_value=None), \
                 patch.object(config.IMAGE_CACHE, 'get_sync', return_value=source), \
                 patch.object(Poster, '_scrape_character_info', side_effect=[{'name': 'Old'}, {'name': 'New'}]) as scrape, \
                 patch.object(Poster, '_draw_poster', side_effect=lambda char, mask, info: Image.new('RGB', (1600, 2100), 'red' if info['name'] == 'Old' else 'green')) as draw:
                cog = Poster(MagicMock())
                cog.assets_dir = assets
                cog._cache.ttl = 60
                cog._render_poster('123')
                info_path = cog._cache.path('info', cog._info_cache_key('123'))
                os.utime(info_path, (1000, 1000))
                (assets / 'new.png').write_bytes(b'new asset')
                # The new assets key creates a PNG just before the old metadata expires.
                with patch('poster_cache.time.time', return_value=1059):
                    old_png = cog._render_poster('123')
                for png in cog._cache.directory.glob('*.png'):
                    os.utime(png, (1059, 1059))
                with patch('poster_cache.time.time', return_value=1061):
                    fresh_png = cog._render_poster('123')
                self.assertEqual(scrape.call_count, 2)
                self.assertEqual(draw.call_count, 3)
                self.assertNotEqual(old_png, fresh_png)
                with Image.open(io.BytesIO(fresh_png)) as image:
                    self.assertEqual(image.getpixel((0, 0)), (0, 128, 0))

    def test_dynamic_country_flags_add_replace_remove_invalidate_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / 'assets'
            assets.mkdir()
            source = root / 'source.png'
            Image.new('RGB', (8, 8)).save(source)
            with patch.object(config, '_DATA_DIR', directory), patch('setup_fonts.find_japanese_font', return_value=None), \
                 patch.object(config.IMAGE_CACHE, 'get_sync', return_value=source), \
                 patch.object(Poster, '_scrape_character_info', return_value={'name': 'A', 'country': 'Peaceful'}) as scrape, \
                 patch.object(Poster, '_draw_poster', side_effect=lambda *args: Image.new('RGB', (1600, 2100))) as draw:
                cog = Poster(MagicMock())
                cog.assets_dir = assets
                cog._render_poster('123')
                cog._render_poster('123')
                self.assertEqual(draw.call_count, 1)
                flag = assets / 'Peaceful.png'
                flag.write_bytes(b'first flag')
                cog._render_poster('123')
                self.assertEqual(draw.call_count, 2)
                flag.write_bytes(b'replaced flag')
                cog._render_poster('123')
                self.assertEqual(draw.call_count, 3)
                flag.unlink()
                # Returning to the original assets set can reuse its original cached PNG.
                cog._render_poster('123')
                self.assertEqual(draw.call_count, 3)
                scrape.assert_called_once()

    def test_completed_cache_reused_after_restart_and_asset_change_reuses_info(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.png'
            Image.new('RGB', (8, 8)).save(source)
            with patch.object(config, '_DATA_DIR', directory), patch('setup_fonts.find_japanese_font', return_value=None), \
                 patch.object(config.IMAGE_CACHE, 'get_sync', return_value=source) as download, \
                 patch.object(Poster, '_scrape_character_info', return_value={'name': 'A'}) as scrape, \
                 patch.object(Poster, '_draw_poster', side_effect=lambda *args: Image.new('RGB', (1600, 2100))) as draw:
                first = Poster(MagicMock())
                output = first._render_poster('123')
                restarted = Poster(MagicMock())
                self.assertEqual(restarted._render_poster('123'), output)
                scrape.assert_called_once()
                draw.assert_called_once()
                download.assert_called_once()
                asset = root / 'flag.png'
                asset.write_bytes(b'changed asset')
                restarted.peaceful_path = str(asset)
                restarted._render_poster('123')
                self.assertEqual(draw.call_count, 2)
                scrape.assert_called_once()

    def test_ttl_corrupt_cache_disk_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = PosterCache(directory, ttl=60, max_entries=3)
            with patch('poster_cache.time.time', return_value=100):
                cache.put('info', '1', {'name': 'A'})
            self.assertEqual(cache.get('info', '1'), {'name': 'A'})
            future = cache.path('info', '1').stat().st_mtime + 61
            with patch('poster_cache.time.time', return_value=future):
                self.assertIsNone(cache.get('info', '1'))
            cache.path('info', '1').write_text('bad')
            self.assertIsNone(cache.get('info', '1'))
            for number in range(10): cache.put('info', str(number), {'name': 'A'})
            self.assertLessEqual(len(list(Path(directory).iterdir())), 3)


class HelpAndErrorTests(unittest.IsolatedAsyncioTestCase):
    def test_test_bootstrap_isolates_all_default_image_assets(self):
        directory = Path(config._DATA_DIR).resolve()
        self.assertNotEqual(directory, Path(config.__file__).resolve().parent / 'data')
        for path in [config.POSTER_MASK_PATH, config.POSTER_PEACEFUL_PATH, config.POSTER_BRAVE_PATH,
                     config.POSTER_GLORY_PATH, config.POSTER_FREEDOM_PATH]:
            self.assertTrue(Path(path).resolve().is_relative_to(directory))
        cog = Poster(MagicMock())
        self.assertEqual(cog.assets_dir.resolve(), directory / 'assets')

    async def test_lottery_excludes_invoker_and_bots(self):
        item = interaction()
        role = MagicMock()
        role.members = [MagicMock(id=99, bot=False), MagicMock(id=1, bot=True)]
        await Lottery.lottery.callback(Lottery(MagicMock()), item, role, 1)
        self.assertIn('不足', item.response.send_message.call_args.args[0])
        item.response.send_message.reset_mock()
        winner = MagicMock(id=2, bot=False)
        winner.display_name = 'Winner'
        role.members.append(winner)
        item.channel.send = AsyncMock()
        with patch('cogs.lottery.asyncio.sleep', new=AsyncMock()):
            await Lottery.lottery.callback(Lottery(MagicMock()), item, role, 1, interval=5)
        result = item.channel.send.call_args.kwargs['embed']
        self.assertIn('Winner', result.description)
        self.assertNotIn('99', result.description)

    async def test_help_lists_every_loaded_command_and_can_page(self):
        bot = FunToolsBot()
        try:
            from cogs.oracle import Oracle
            from cogs.lottery import Lottery
            for cog in [Birthday(bot), Oracle(bot), Lottery(bot), Poster(bot), Quotes(bot), Help(bot), RoleTools(bot)]:
                await bot.add_cog(cog)
            item = interaction()
            item.guild_id = None
            await Help.help_command.callback(bot.get_cog('Help'), item)
            view = item.response.send_message.call_args.kwargs['view']
            self.assertEqual({c.name for c in view.records}, {c.name for c in bot.tree.get_commands()})
            self.assertIn('remove-role', {c.name for c in view.records})
            self.assertIn('quote_add', {c.name for c in view.records})
            await view.next.callback(item)
            self.assertEqual(view.page, 1)
            # Serialize the real application command schema, including hyphenated name and choices.
            for command in bot.tree.get_commands():
                self.assertTrue(command.to_dict(bot.tree)['name'])
        finally:
            await bot.close()

    async def test_error_initial_deferred_and_permission_responses(self):
        for done in (False, True):
            item = interaction()
            item.response.is_done.return_value = done
            await send_error(item, discord.app_commands.MissingPermissions(['manage_roles']))
            sender = item.followup.send if done else item.response.send_message
            self.assertTrue(sender.call_args.kwargs['ephemeral'])
            self.assertIn('権限', sender.call_args.args[0])

    def test_prepared_font_is_loaded_without_network(self):
        with patch('image_cache.download_bytes', side_effect=AssertionError('no network')):
            prepared = setup_fonts.find_japanese_font()
            if prepared:
                self.assertEqual(setup_fonts.prepare_japanese_font(), prepared)
            else:
                cog = Poster(MagicMock())
                with self.assertRaises(ValueError):
                    cog._try_load_font('', 24)
