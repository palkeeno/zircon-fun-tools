import asyncio
import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import config
import utils
from cogs.birthday import Birthday
from cogs.quotes import Quotes
class BirthdayFixTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.cog = Birthday.__new__(Birthday)
        self.cog.bot = MagicMock()
        self.cog.tz = utils.get_timezone()
        self.cog._data_lock = asyncio.Lock()
        self.cog.defaults = {'hour': 9}
        self.cog.settings = {'hour': 9}
        self.cog.birthdays = [{'character_id': '1', 'month': 10, 'day': 9, 'reported': False}]
        self.interaction = MagicMock()
        self.interaction.response = AsyncMock()
        self.interaction.followup = AsyncMock()

    async def test_failed_post_not_marked_reported(self):
        self.cog._announce_zircon_birthday = AsyncMock(return_value=False)
        with patch('config.get_birthday_channel_id', return_value=123):
            self.assertFalse(await self.cog._announce_today_birthdays(datetime.datetime(2026, 10, 9)))
        self.assertFalse(self.cog.birthdays[0]['reported'])

    async def test_partial_failure_then_retry_only_pending(self):
        self.cog.birthdays.append({'character_id': '2', 'month': 10, 'day': 9, 'reported': False})
        self.cog._announce_zircon_birthday = AsyncMock(side_effect=[True, False, True])
        self.cog.save_birthdays = MagicMock()
        with patch('config.get_birthday_channel_id', return_value=123):
            self.assertFalse(await self.cog._announce_today_birthdays(datetime.datetime(2026, 10, 9)))
            self.assertTrue(self.cog.birthdays[0]['reported'])
            self.assertTrue(await self.cog._announce_today_birthdays(datetime.datetime(2026, 10, 9)))
        self.assertEqual(self.cog._announce_zircon_birthday.await_count, 3)

    async def test_zero_valid_rows_preserves_existing(self):
        file = MagicMock(filename='birthdays.json')
        file.read = AsyncMock(return_value=b'[{"character_id":"2","month":2,"day":31}]')
        original = self.cog.birthdays
        self.cog.save_birthdays = MagicMock()
        await Birthday.birthday_update.callback(self.cog, self.interaction, file)
        self.assertIs(self.cog.birthdays, original)
        self.cog.save_birthdays.assert_not_called()

    async def test_save_failure_rolls_back_memory(self):
        file = MagicMock(filename='birthdays.json')
        file.read = AsyncMock(return_value=b'[{"character_id":"2","month":2,"day":29}]')
        original = self.cog.birthdays
        self.cog.save_birthdays = MagicMock(side_effect=OSError('disk failure'))
        await Birthday.birthday_update.callback(self.cog, self.interaction, file)
        self.assertIs(self.cog.birthdays, original)

    def test_catch_up_after_scheduled_minute(self):
        self.assertTrue(self.cog._is_scheduled_time(datetime.datetime(2026, 10, 9, 9, 5)))
        self.assertFalse(self.cog._is_scheduled_time(datetime.datetime(2026, 10, 9, 8, 59)))

    def test_management_default_permissions(self):
        for cog, prefix in [(Birthday, 'birthday'), (Quotes, 'quote')]:
            for suffix in ['update', 'toggle', 'schedule']:
                command = getattr(cog, prefix + '_' + suffix)
                self.assertTrue(command.guild_only)
                self.assertTrue(command.default_permissions.administrator)
                self.assertEqual(command.checks, [])

class BirthdayTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.cog = Birthday.__new__(Birthday)
        self.cog.bot = MagicMock()
        self.cog._data_lock = asyncio.Lock()
        self.cog.save_birthdays = MagicMock()
        self.cog.birthdays = [dict(character_id='1', name='A', month=10, day=9, reported=False)]
        self.interaction = MagicMock()
        self.interaction.response = AsyncMock()
        self.interaction.followup = AsyncMock()

    async def test_legacy_duplicates_announced_once(self):
        self.cog.birthdays.append(dict(self.cog.birthdays[0]))
        self.cog._announce_zircon_birthday = AsyncMock(return_value=True)
        with patch('config.get_birthday_channel_id', return_value=123):
            self.assertTrue(await self.cog._announce_today_birthdays(datetime.datetime(2026, 10, 9)))
        self.cog._announce_zircon_birthday.assert_awaited_once()
        self.assertTrue(all((record['reported'] for record in self.cog.birthdays)))

    async def test_import_duplicates_rejected_without_save(self):
        original = self.cog.birthdays
        file = MagicMock(filename='birthdays.json')
        file.read = AsyncMock(return_value=json.dumps([original[0], original[0]]).encode())
        await Birthday.birthday_update.callback(self.cog, self.interaction, file)
        self.assertIs(self.cog.birthdays, original)
        self.cog.save_birthdays.assert_not_called()

    async def test_settings_save_failure_preserves_memory(self):
        self.cog.settings = {'hour': 9, 'enabled': True}
        with patch('config.set_runtime_section', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                await self.cog._change_settings({'enabled': False})
        self.assertTrue(self.cog.settings['enabled'])

    async def test_failed_schedule_minute_catches_up_and_finishes_day(self):
        self.cog.settings = {'hour': 9, 'enabled': True}
        self.cog.defaults = {'hour': 9}
        self.cog.tz = utils.get_timezone()
        self.cog._refresh_daily_flags = MagicMock()
        self.cog._announce_today_birthdays = AsyncMock(side_effect=[False, True])
        target_time = datetime.datetime(2026, 10, 9, 9, 5)
        with patch('cogs.birthday.datetime.datetime') as clock, patch('config.set_runtime_section'):
            clock.now.return_value = target_time
            await Birthday.birthday_task.coro(self.cog)
            self.assertNotIn('last_announced_date', self.cog.settings)
            await Birthday.birthday_task.coro(self.cog)
        self.assertEqual(self.cog.settings['last_announced_date'], '2026-10-09')


class CsvImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_header_csv_is_saved(self):
        cog = Birthday.__new__(Birthday)
        cog._data_lock = asyncio.Lock()
        cog.birthdays = []
        cog.save_birthdays = MagicMock()
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        file = MagicMock(filename="birthdays.csv")
        file.read = AsyncMock(return_value=b'character_id,name,month,day\n1,"A,B",2,29\n')
        await Birthday.birthday_update.callback(cog, interaction, file)
        self.assertEqual(cog.birthdays[0]["name"], "A,B")
        cog.save_birthdays.assert_called_once()

    async def test_invalid_csv_row_preserves_existing(self):
        cog = Birthday.__new__(Birthday)
        cog._data_lock = asyncio.Lock()
        cog.birthdays = [{"character_id": "old"}]
        original = cog.birthdays
        cog.save_birthdays = MagicMock()
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        file = MagicMock(filename="birthdays.csv")
        file.read = AsyncMock(return_value=b'character_id,name,month,day\n1,A,2,29\n2,B,2,31\n')
        await Birthday.birthday_update.callback(cog, interaction, file)
        self.assertIs(cog.birthdays, original)
        cog.save_birthdays.assert_not_called()
