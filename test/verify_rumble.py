import sys
import os
import unittest
import datetime
from unittest.mock import MagicMock, AsyncMock

# Mock openai before import
import sys
from unittest.mock import MagicMock
sys.modules["openai"] = MagicMock()

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.rumble import RumbleEngine, STAGES, get_stage_by_id, generate_narration
import config

class TestRumble(unittest.IsolatedAsyncioTestCase):
    async def test_stage_loading(self):
        print("\nTesting Stage Loading...")
        self.assertTrue(len(STAGES) > 0)
        print(f"Loaded {len(STAGES)} stages.")
        s = get_stage_by_id("cyber_slums")
        self.assertIsNotNone(s)
        self.assertEqual(s.name, "ネオトーキョー・スラム")

    async def test_narration_fallback(self):
        print("\nTesting Narration Fallback...")
        # Ensure no API key
        original_key = config.AI_API_KEY
        config.AI_API_KEY = ""
        
        stage = STAGES[0]
        event = {"type": "attack", "winner": "Taro", "loser": "Jiro", "environment": []}
        
        text = await generate_narration(stage, event)
        print(f"Generated Text: {text}")
        self.assertIn("Taro", text)
        self.assertIn("Jiro", text)
        
        # Restore (though it's process local)
        config.AI_API_KEY = original_key

    async def test_engine_init(self):
        print("\nTesting Engine Initialization...")
        bot = MagicMock()
        now = datetime.datetime.now()
        engine = RumbleEngine(bot, 123, 456, now, "cyber_slums")
        
        self.assertEqual(engine.status, "WAITING")
        self.assertEqual(engine.stage_id, "cyber_slums")
        
        engine.participants.append(111)
        engine.participants.append(222)
        
        data = engine.to_dict()
        engine2 = RumbleEngine.from_dict(bot, data)
        
        self.assertEqual(engine.channel_id, engine2.channel_id)
        self.assertEqual(engine.participants, engine2.participants)

if __name__ == "__main__":
    unittest.main()
