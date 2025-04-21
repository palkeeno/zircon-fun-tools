"""
ランブルゲームのコグ
このモジュールは、ランブルゲームの機能を提供します。
"""

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os
import logging
import traceback
import config

# ロギングの設定
logger = logging.getLogger(__name__)

class RambleGame(commands.Cog):
    """
    ランブルゲームのコグ
    ランブルゲームの機能を提供します。
    """
    
    def __init__(self, bot: commands.Bot):
        """
        ランブルゲームのコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot
        self.active_games: Dict[int, Dict] = {}  # {guild_id: game_data}
        self.players: Dict[int, Dict] = {}  # {player_id: player_data}
        self.game_file = "data/game_data.json"
        self.settings_file = "data/game_settings.json"
        self.load_game_data()
        self.load_settings()

    def load_game_data(self):
        """ゲームデータを読み込む"""
        if not os.path.exists(self.game_file):
            os.makedirs(os.path.dirname(self.game_file), exist_ok=True)
            with open(self.game_file, 'w') as f:
                json.dump({}, f)
            return
        
        with open(self.game_file, 'r') as f:
            data = json.load(f)
            self.players = data.get('players', {})

    def load_settings(self):
        """設定ファイルを読み込む"""
        if not os.path.exists(self.settings_file):
            raise FileNotFoundError("設定ファイルが見つかりません")
        
        with open(self.settings_file, 'r', encoding='utf-8') as f:
            self.settings = json.load(f)

    def save_game_data(self):
        """ゲームデータを保存"""
        with open(self.game_file, 'w') as f:
            json.dump({'players': self.players}, f, indent=4)

    def format_message(self, template: str, **kwargs) -> str:
        """メッセージテンプレートをフォーマット"""
        # ランダムな環境要素を追加
        if "location" in kwargs:
            location = next(loc for loc in self.settings["arena"]["locations"] if loc["name"] == kwargs["location"])
            kwargs["environment"] = random.choice([location["environment"], random.choice(self.settings["environments"])])
            kwargs["mood"] = location["mood"]
            if "trap" not in kwargs:
                kwargs["trap"] = random.choice(location["traps"])
        
        # ランダムな武器要素を追加
        if "weapon" in kwargs:
            weapon = next(w for w in self.settings["weapons"] if w["name"] == kwargs["weapon"])
            kwargs["special"] = weapon["special"]
            kwargs["element"] = weapon["element"]
        
        return template.format(**kwargs)

    def get_random_location(self) -> Dict:
        """ランダムな場所を取得"""
        return random.choice(self.settings["arena"]["locations"])

    def get_random_weapon(self) -> Dict:
        """ランダムな武器を取得"""
        return random.choice(self.settings["weapons"])

    def get_random_action(self, action_type: str, success: bool = True) -> str:
        """ランダムな行動テキストを取得"""
        templates = self.settings["action_templates"][action_type]
        if isinstance(templates, dict):
            templates = templates["success" if success else "fail"]
        
        # テンプレートを選択し、必要に応じて要素を組み合わせる
        template = random.choice(templates)
        
        # シチュエーションを強調するために、時々「突然」や「突然の」を追加
        if random.random() < 0.3 and "{location}" in template:
            template = template.replace("{location}", "突然の{location}")
        
        return template

    class JoinButton(ui.Button):
        def __init__(self):
            super().__init__(label="参加", style=discord.ButtonStyle.green)

        async def callback(self, interaction: discord.Interaction):
            game = self.view.game
            if interaction.user.id in game.active_games[interaction.guild_id]["players"]:
                await interaction.response.send_message("すでに参加しています！", ephemeral=True)
                return

            game.active_games[interaction.guild_id]["players"][interaction.user.id] = {
                "name": interaction.user.name,
                "alive": True,
                "kills": 0,
                "zircons": 0,
                "relics": 0,
                "rank": 0,
                "location": None,
                "weapon": None
            }
            await interaction.response.send_message("参加登録しました！", ephemeral=True)

    class GameView(ui.View):
        def __init__(self, game):
            super().__init__(timeout=None)
            self.game = game
            self.add_item(game.JoinButton())

    async def _is_operator(self, interaction: discord.Interaction) -> bool:
        """
        運営ロールIDで判定します。
        """
        from config import OPERATOR_ROLE_ID
        if not OPERATOR_ROLE_ID or not hasattr(interaction.user, "roles"):
            return False
        return any(role.id == OPERATOR_ROLE_ID for role in interaction.user.roles)

    @app_commands.command(
        name="ramble_game",
        description="ランブルゲームを開始します"
    )
    async def ramble_game(self, interaction: discord.Interaction):
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        if not config.is_feature_enabled('ramble'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
            return

        try:
            # ゲームの初期化処理
            await interaction.response.send_message(
                "ランブルゲームを開始します！",
                ephemeral=True
            )
            # ここにゲームのロジックを実装
        except Exception as e:
            logger.error(f"Error in start_ramble_game: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    async def send_countdown(self, channel, start_time):
        """カウントダウンメッセージを送信"""
        remaining = start_time - datetime.now()
        if remaining.total_seconds() > 120:
            await asyncio.sleep(remaining.total_seconds() - 120)
            await channel.send("🕒 ゲーム開始まであと2分！")
        if remaining.total_seconds() > 60:
            await asyncio.sleep(60)
            await channel.send("🕒 ゲーム開始まであと1分！")
        if remaining.total_seconds() > 30:
            await asyncio.sleep(30)
            await channel.send("🕒 ゲーム開始まであと30秒！")
        if remaining.total_seconds() > 10:
            await asyncio.sleep(20)
            await channel.send("🕒 ゲーム開始まであと10秒！")
        
        await asyncio.sleep(10)
        await self.start_game(channel)

    async def start_game(self, channel):
        """ゲームを開始"""
        game_data = self.active_games[channel.guild.id]
        game_data["status"] = "playing"
        game_data["round"] = 1

        # 参加者一覧を表示
        players = [f"<@{player_id}>" for player_id in game_data["players"].keys()]
        embed = discord.Embed(
            title="🎮 ランブルゲーム開始！",
            description="ゲームが始まりました！\n参加者一覧：\n" + "\n".join(players),
            color=discord.Color.green()
        )
        await channel.send(embed=embed)

        # ゲームループ
        while len([p for p in game_data["players"].values() if p["alive"]]) > 1:
            await self.play_round(channel)
            game_data["round"] += 1
            await asyncio.sleep(5)  # ラウンド間の待機時間

        # ゲーム終了処理
        await self.end_game(channel)

    async def play_round(self, channel):
        """1ラウンドのゲームを進行"""
        game_data = self.active_games[channel.guild.id]
        alive_players = [p for p in game_data["players"].items() if p[1]["alive"]]
        
        # ラウンド開始メッセージ
        embed = discord.Embed(
            title=f"🎮 ラウンド {game_data['round']}",
            description="新しいラウンドが始まります！",
            color=discord.Color.blue()
        )
        await channel.send(embed=embed)

        # ランダムに6-10人のプレイヤーを選択
        num_actions = random.randint(6, min(10, len(alive_players)))
        active_players = random.sample(alive_players, num_actions)

        # 各プレイヤーの行動を決定
        for player_id, player_data in active_players:
            # プレイヤーの位置を更新
            location = self.get_random_location()
            player_data["location"] = location["name"]

            # 行動を決定
            action = random.choice(["attack", "search", "run", "nothing"])
            
            if action == "attack":
                # 攻撃対象を選択
                target = random.choice([p for p in alive_players if p[0] != player_id])
                weapon = self.get_random_weapon()
                player_data["weapon"] = weapon["name"]

                # 攻撃成功確率（武器の種類と属性に応じて変化）
                success_chance = 0.7
                if weapon["type"] == "遠距離":
                    success_chance += 0.1
                if weapon["element"] == location["environment"]:
                    success_chance += 0.15
                
                if random.random() < success_chance:
                    game_data["players"][target[0]]["alive"] = False
                    game_data["players"][player_id]["kills"] += 1
                    
                    # 攻撃成功メッセージ
                    message = self.format_message(
                        self.get_random_action("attack", True),
                        attacker=f"<@{player_id}>",
                        target=f"<@{target[0]}>",
                        weapon=weapon["name"],
                        body_part=random.choice(self.settings["body_parts"]),
                        location=location["name"]
                    )
                    await channel.send(message)
                else:
                    # 攻撃失敗メッセージ
                    message = self.format_message(
                        self.get_random_action("attack", False),
                        attacker=f"<@{player_id}>",
                        target=f"<@{target[0]}>",
                        weapon=weapon["name"],
                        defense=random.choice(self.settings["defenses"]),
                        location=location["name"]
                    )
                    await channel.send(message)
            
            elif action == "search":
                # アイテム発見確率（場所の特性に応じて変化）
                success_chance = 0.3
                if location["environment"] in ["幻想的", "神秘的"]:
                    success_chance += 0.1
                
                if random.random() < success_chance:
                    item = random.choice(["zircon", "relic"])
                    if item == "zircon":
                        game_data["players"][player_id]["zircons"] += 1
                        game_data["players"][player_id]["points"] += self.settings["items"]["zircon"]["points"]
                    else:
                        game_data["players"][player_id]["relics"] += 1
                        game_data["players"][player_id]["points"] += self.settings["items"]["relic"]["points"]
                    
                    # アイテム発見メッセージ
                    message = self.format_message(
                        self.get_random_action("search", True),
                        player=f"<@{player_id}>",
                        location=location["name"],
                        item=self.settings["items"][item]["name"]
                    )
                    await channel.send(message)
                else:
                    # 探索失敗メッセージ
                    message = self.format_message(
                        self.get_random_action("search", False),
                        player=f"<@{player_id}>",
                        location=location["name"]
                    )
                    await channel.send(message)

            elif action == "run":
                # 逃走メッセージ
                message = self.format_message(
                    self.get_random_action("run"),
                    player=f"<@{player_id}>",
                    location=location["name"]
                )
                await channel.send(message)

            else:  # nothing
                # 何もしないメッセージ
                message = self.format_message(
                    self.get_random_action("nothing"),
                    player=f"<@{player_id}>",
                    location=location["name"]
                )
                await channel.send(message)

            # 突然死の可能性（場所の危険度に応じて変化）
            death_chance = 0.1
            if location["mood"] in ["危険", "過酷"]:
                death_chance += 0.05
            
            if random.random() < death_chance:
                game_data["players"][player_id]["alive"] = False
                message = self.format_message(
                    self.get_random_action("sudden_death"),
                    player=f"<@{player_id}>",
                    location=location["name"]
                )
                await channel.send(message)

            # 復活イベント（場所の特性に応じて変化）
            revive_chance = 0.05
            if location["environment"] in ["幻想的", "神秘的"]:
                revive_chance += 0.02
            
            if random.random() < revive_chance:
                dead_players = [p for p in game_data["players"].items() if not p[1]["alive"]]
                if dead_players:
                    revived = random.choice(dead_players)
                    game_data["players"][revived[0]]["alive"] = True
                    await channel.send(f"<@{revived[0]}> が復活しました！")

    async def end_game(self, channel):
        """ゲームを終了し、結果を表示"""
        game_data = self.active_games[channel.guild.id]
        
        # ポイント計算
        for player_id, player_data in game_data["players"].items():
            points = 0
            # 生存ポイント（最後まで生き残った順位に応じて）
            if player_data["alive"]:
                points += 10000
            # キルポイント
            points += player_data["kills"] * 100
            # ジルコンポイント
            points += player_data["zircons"] * 50
            # レリックポイント
            points += player_data["relics"] * 200
            player_data["points"] = points

        # 順位付け
        sorted_players = sorted(
            game_data["players"].items(),
            key=lambda x: x[1]["points"],
            reverse=True
        )
        
        # 結果を表示
        embed = discord.Embed(
            title="🏆 ゲーム終了！",
            description="最終結果",
            color=discord.Color.gold()
        )
        
        for i, (player_id, data) in enumerate(sorted_players, 1):
            embed.add_field(
                name=f"{i}位: {data['name']}",
                value=f"ポイント: {data['points']}\nキル: {data['kills']}\nジルコン: {data['zircons']}\nレリック: {data['relics']}",
                inline=False
            )

        await channel.send(embed=embed)
        
        # ゲームデータをクリア
        del self.active_games[channel.guild.id]

async def setup(bot: commands.Bot):
    """
    コグをボットに追加します。
    
    Args:
        bot (commands.Bot): ボットのインスタンス
    """
    try:
        await bot.add_cog(RambleGame(bot))
        logger.info("RambleGame cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load RambleGame cog: {e}")
        logger.error(traceback.format_exc())
        raise