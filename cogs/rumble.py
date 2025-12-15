"""
Rumble Royale Cog
バトルロイヤル形式のミニゲーム機能を提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
import logging
import json
import os
import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import config
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    logging.warning("OpenAI module not found. AI features will be disabled.")

# ロギング設定
logger = logging.getLogger(__name__)

# 定数
GAME_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'rumble_state.json')

@dataclass
class Stage:
    id: str
    name: str
    description: str
    keywords: List[str]
    tone: str

STAGES = [
    Stage(
        id="cyber_slums",
        name="ネオトーキョー・スラム",
        description="酸性雨が降り注ぐ、ネオン輝く荒廃した未来都市の路地裏。",
        keywords=["ネオン", "酸性雨", "錆びたパイプ", "ホログラム広告", "蒸気"],
        tone="サイバーパンク、退廃的、冷徹"
    ),
    Stage(
        id="ancient_ruins",
        name="忘却の古代遺跡",
        description="密林に埋もれた、未知の文明が残した巨大な石造建築群。",
        keywords=["苔むした石柱", "絡みつく蔦", "崩れかけた祭壇", "謎の象形文字", "静寂"],
        tone="神秘的、静謐、不気味"
    ),
    Stage(
        id="magma_chamber",
        name="灼熱の大空洞",
        description="煮えたぎるマグマが流れる地下の大洞窟。熱気で視界が歪む。",
        keywords=["マグマ", "噴き出す蒸気", "崩れる足場", "硫黄の臭い", "灼熱"],
        tone="激しい、危険、熱狂的"
    ),
    Stage(
        id="haunted_hospital",
        name="廃病院",
        description="長年放置され、不気味な噂が絶えない閉鎖された病院。",
        keywords=["割れた窓ガラス", "赤錆びたベッド", "点滅する蛍光灯", "長い廊下", "散らばったカルテ"],
        tone="ホラー、陰湿、狂気"
    ),
        Stage(
        id="cherry_blossom",
        name="桜舞う古都",
        description="満開の桜が咲き乱れる、美しいがどこか儚い古い都。",
        keywords=["桜吹雪", "石畳", "朱色の橋", "川のせせらぎ", "提灯"],
        tone="美しい、儚い、和風"
    )
]

def get_stage_by_id(stage_id: str) -> Optional[Stage]:
    for s in STAGES:
        if s.id == stage_id:
            return s
    return None

class JoinView(discord.ui.View):
    """参加受付用のView"""
    def __init__(self):
        super().__init__(timeout=None) # 永続表示（タスクで管理するため）

    @discord.ui.button(label="参加する", style=discord.ButtonStyle.success, emoji="⚔️", custom_id="rumble_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 既に参加済みかチェックはEngine側でやる、あるいはここで簡易チェック
        # このViewは永続化される可能性があるため、Engineへの参照を持たせるのが難しい場合がある。
        # ここではinteraction.client (bot) 経由でCogを取得して処理を委譲する。
        cog = interaction.client.get_cog("Rumble")
        if cog:
            await cog.register_participant(interaction)
        else:
            await interaction.response.send_message("エラー: Rumble機能が見つかりません。", ephemeral=True)

class StageSelectView(discord.ui.View):
    """ステージ選択用のView"""
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.selected_stage_id: Optional[str] = None
        
        # Select Menuの作成
        options = [
            discord.SelectOption(label=s.name, description=s.description[:50], value=s.id)
            for s in STAGES
        ]
        
        select = discord.ui.Select(placeholder="ステージ（時代）を選択してください", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("ステージ選択はコマンド実行者のみ可能です。", ephemeral=True)
            return
        
        select_item = self.children[0] # The Select item
        self.selected_stage_id = select_item.values[0]
        await interaction.response.send_message(f"ステージを「{get_stage_by_id(self.selected_stage_id).name}」に設定しました。", ephemeral=True)
        self.stop()

async def generate_narration(stage: Stage, event_data: dict) -> str:
    """AIを使用してナレーションを生成する"""
    if not config.AI_API_KEY:
        # フォールバック（APIキーがない場合）
        winner = event_data.get('winner', '誰か')
        loser = event_data.get('loser', '誰か')
        etype = event_data.get('type')
        if etype == 'attack':
            return f"{winner}の攻撃！ {loser}は倒れた。"
        elif etype == 'ambush':
            return f"{winner}が奇襲を仕掛けた！ {loser}はなすすべなく脱落した。"
        elif etype == 'trap':
            return f"{winner}が仕掛けた罠に{loser}がかかった！"
        elif etype == 'accident':
            return f"不運な事故により、{loser}が脱落した。"
        else:
            return f"{loser}が脱落した。"

    system_prompt = f"""
あなたはバトルロイヤルゲームの実況AIです。
以下の情報を元に、プレイヤーの行動や結果を描写するナレーションを作成してください。

# ステージ情報
名前: {stage.name}
雰囲気: {stage.description}
トーン: {stage.tone}
環境要素: {", ".join(stage.keywords)}

# 出力要件
- 言語: 日本語
- 長さ: 2〜3文の短文
- 内容: 戦闘、事故、脱落の状況を臨場感たっぷりに描写してください。
- 注意: 過度に残酷・グロテスクな表現は避けてください。ゲーム的な表現（「HPが0になった」など）ではなく、小説的な描写にしてください。
"""
    
    user_prompt = f"""
# イベント情報
{json.dumps(event_data, ensure_ascii=False)}

このイベントの様子を描写してください。
"""

    try:
        if config.AI_PROVIDER == 'openai':
            client = OpenAI(api_key=config.AI_API_KEY)
            response = client.chat.completions.create(
                model=config.AI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=150,
                temperature=0.8
            )
            return response.choices[0].message.content.strip()
        # Gemini実装が必要ならここに追加
        else:
            return "（AIプロバイダー設定エラー: ナレーション生成スキップ）"
    except Exception as e:
        logger.error(f"AI generation failed: {e}")
        return f"激しい戦いの末、{event_data.get('winner', '')}が{event_data.get('loser', '')}を倒した。（通信エラーにより詳細描写なし）"


class RumbleEngine:
    def __init__(self, bot, guild_id: int, channel_id: int, start_time: datetime.datetime, stage_id: str):
        self.bot = bot
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.start_time = start_time
        self.stage_id = stage_id
        self.participants: List[int] = [] # User IDs
        self.alive: List[int] = []        # User IDs
        self.status = "WAITING"           # WAITING, IN_PROGRESS, FINISHED
        self.message_id: Optional[int] = None # 募集メッセージID

    def to_dict(self):
        return {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "start_time": self.start_time.isoformat(),
            "stage_id": self.stage_id,
            "participants": self.participants,
            "alive": self.alive,
            "status": self.status,
            "message_id": self.message_id
        }

    @classmethod
    def from_dict(cls, bot, data):
        # 過去の時刻の場合は現在時刻+1分とかに補正するか、あるいは期限切れとして処理するか
        # ここではそのまま復元
        obj = cls(
            bot,
            data["guild_id"],
            data["channel_id"],
            datetime.datetime.fromisoformat(data["start_time"]),
            data["stage_id"]
        )
        obj.participants = data["participants"]
        obj.alive = data["alive"]
        obj.status = data["status"]
        obj.message_id = data.get("message_id")
        return obj

    async def run_game_loop(self):
        """ゲームのメインループ"""
        self.status = "IN_PROGRESS"
        
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logger.error(f"Channel {self.channel_id} not found. Game aborted.")
            return

        stage = get_stage_by_id(self.stage_id)
        if not stage:
            stage = random.choice(STAGES)
            self.stage_id = stage.id

        await channel.send(f"🌋 **Rumble Royale 開始！** 🌋\nステージ: **{stage.name}**\n{stage.description}\n生存者: {len(self.alive)}名")
        
        # 参加者全員のリストを表示
        mentions = [f"<@{uid}>" for uid in self.alive]
        await channel.send(f"参加者: {' '.join(mentions)}")
        
        await asyncio.sleep(5)

        turn = 1
        while len(self.alive) > 1:
            # 1ターン処理
            await asyncio.sleep(8) # 演出用ウェイト

            # イベント発生抽選
            # ランダムに2名選出（攻撃者と被害者）
            # もしくは1名（事故）
            
            attacker_id = random.choice(self.alive)
            targets = [u for u in self.alive if u != attacker_id]
            
            if not targets: # 残り1人（ループ条件で弾かれるはずだが念の為）
                break
                
            # イベントタイプ決定
            dice = random.random()
            event_type = "attack"
            target_id = None
            
            if dice < 0.6:
                event_type = "attack"
                target_id = random.choice(targets)
            elif dice < 0.8:
                event_type = "ambush"
                target_id = random.choice(targets)
            elif dice < 0.9:
                event_type = "trap"
                target_id = random.choice(targets)
            else:
                event_type = "accident" # 攻撃者は関係なく誰かが事故る
                attacker_id = None # Accidentでは攻撃者はいないことにする（あるいは環境）
                target_id = random.choice(self.alive) # 自分も含むアヒャ

            # 脱落判定
            # 簡易的に、選ばれたら即脱落とする
            loser_id = target_id
            winner_id = attacker_id if attacker_id else None # Accidentの場合はWinnerなし

            if winner_id == loser_id: # 自分自身のトラップや事故
                winner_id = None 
            
            # 生存者リスト更新
            if loser_id in self.alive:
                self.alive.remove(loser_id)

            # 名前取得（キャッシュやfetch）
            try:
                guild = self.bot.get_guild(self.guild_id)
                loser_member = guild.get_member(loser_id) or await guild.fetch_member(loser_id)
                loser_name = loser_member.display_name
                
                winner_name = "謎の影"
                if winner_id:
                    winner_member = guild.get_member(winner_id) or await guild.fetch_member(winner_id)
                    winner_name = winner_member.display_name
                elif event_type == "accident":
                    winner_name = "環境"
            except:
                loser_name = "Unknown"
                winner_name = "Unknown"

            # イベントデータ作成
            event_data = {
                "type": event_type,
                "winner": winner_name if winner_id else None,
                "loser": loser_name,
                "environment": stage.keywords
            }

            # AIナレーション生成
            narration = await generate_narration(stage, event_data)

            # 結果表示
            embed = discord.Embed(title=f"Turn {turn} - {event_type.upper()}", description=narration, color=discord.Color.red())
            embed.add_field(name="脱落", value=f"💀 **{loser_name}**")
            if winner_id:
                embed.add_field(name="生存（勝者）", value=f"⚔️ {winner_name}")
            embed.set_footer(text=f"残り生存者: {len(self.alive)}名")
            
            await channel.send(embed=embed)
            turn += 1

        # 決着
        await asyncio.sleep(3)
        if self.alive:
            champion_id = self.alive[0]
            await channel.send(f"👑 **優勝者は <@{champion_id}> です！** おめでとうございます！🎉")
        else:
            await channel.send("💀 **全員脱落しました...** 勝者なし。")
        
        self.status = "FINISHED"


class Rumble(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.games: Dict[int, RumbleEngine] = {} # channel_id -> Engine
        self.check_schedule_task.start()
        self._load_state()

    def cog_unload(self):
        self.check_schedule_task.cancel()
        self._save_state()

    def _save_state(self):
        data = [game.to_dict() for game in self.games.values() if game.status == "WAITING"]
        try:
            with open(GAME_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _load_state(self):
        if not os.path.exists(GAME_STATE_FILE):
            return
        try:
            with open(GAME_STATE_FILE, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
                for data in data_list:
                    # 古いデータはスキップするなどバリデーションが必要だが、一旦全て読み込む
                    try:
                        engine = RumbleEngine.from_dict(self.bot, data)
                        # EngineのチャンネルIDをキーにする（1チャンネル1ゲーム想定）
                        self.games[engine.channel_id] = engine
                        logger.info(f"Loaded rumble game for channel {engine.channel_id}")
                    except Exception as e:
                        logger.error(f"Failed to load game: {e}")
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")

    @tasks.loop(seconds=60)
    async def check_schedule_task(self):
        """1分ごとにスケジュールを確認して開始する"""
        now = datetime.datetime.now().astimezone() # Aware
        
        # 削除リスト
        to_remove = []

        for channel_id, engine in self.games.items():
            if engine.status == "WAITING":
                # タイムゾーン考慮: engine.start_time は保存時にisoformatされているのでawareかconfirmが必要
                # fromisoformatでawareになるはず
                if engine.start_time <= now:
                    if len(engine.participants) < 2:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send("⚠️ 参加者が不足しているため、Rumbleを中止しました。（最低2名）")
                        engine.status = "FINISHED" # 終了扱い
                        to_remove.append(channel_id)
                    else:
                        # ゲーム開始
                        engine.alive = list(engine.participants)
                        # ゲームループは非同期で走らせる
                        asyncio.create_task(engine.run_game_loop())
            elif engine.status == "FINISHED":
                to_remove.append(channel_id)

        # 終了したゲームを辞書から削除
        for cid in to_remove:
            self.games.pop(cid, None)
        
        # 定期的に保存
        self._save_state()

    @check_schedule_task.before_loop
    async def before_check_schedule(self):
        await self.bot.wait_until_ready()

    async def register_participant(self, interaction: discord.Interaction):
        """参加ボタン処理"""
        engine = self.games.get(interaction.channel_id)
        if not engine or engine.status != "WAITING":
            await interaction.response.send_message("現在、このチャンネルで募集中のRumbleはありません。", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id in engine.participants:
            await interaction.response.send_message("既に参加済みです！", ephemeral=True)
            return

        engine.participants.append(user_id)
        self._save_state() # 状態が変わったので保存
        await interaction.response.send_message(f"参加を受け付けました！現在の参加者数: {len(engine.participants)}人", ephemeral=True)

    @app_commands.command(name="rumble", description="バトルロイヤルゲームを開始またはスケジュールします")
    @app_commands.describe(start_time="開始時刻 (例: 21:00, 2025-01-01 21:00) 省略時は5分後")
    async def rumble(self, interaction: discord.Interaction, start_time: str = None):
        channel_id = interaction.channel_id
        if channel_id in self.games and self.games[channel_id].status != "FINISHED":
             await interaction.response.send_message("このチャンネルでは既にRumbleが進行中または募集中です。", ephemeral=True)
             return

        # 時間解析
        now = datetime.datetime.now().astimezone()
        target_time = None
        
        if start_time:
            # 様々なフォーマットに対応を試みる
            formats = ["%Y-%m-%d %H:%M", "%H:%M"]
            parsed = None
            for fmt in formats:
                try:
                    dt = datetime.datetime.strptime(start_time, fmt)
                    # 年月日がない場合は今日の日付を補完
                    if fmt == "%H:%M":
                        dt = now.replace(hour=dt.hour, minute=dt.minute, second=0, microsecond=0)
                        if dt < now: # 過去なら明日
                            dt += datetime.timedelta(days=1)
                    parsed = dt.astimezone() if dt.tzinfo else dt.replace(tzinfo=now.tzinfo) # Aware化
                    break
                except ValueError:
                    continue
            
            if parsed:
                target_time = parsed
            else:
                await interaction.response.send_message("時刻の形式が正しくありません。「21:00」または「2025-01-01 21:00」のように指定してください。", ephemeral=True)
                return
        else:
            # デフォルト5分後
            target_time = now + datetime.timedelta(minutes=5)
            
        if target_time <= now:
             await interaction.response.send_message("開始時刻は未来を指定してください。", ephemeral=True)
             return

        # Engine作成
        engine = RumbleEngine(
            bot=self.bot,
            guild_id=interaction.guild_id,
            channel_id=channel_id,
            start_time=target_time,
            stage_id="" # 後で選択
        )
        self.games[channel_id] = engine

        # ステージ選択ビュー
        view_stage = StageSelectView(interaction.user.id)
        
        # 最初の応答 (Ephemeralでステージ選択)
        await interaction.response.send_message(
            f"Rumble Royaleを **{target_time.strftime('%Y-%m-%d %H:%M')}** にスケジュールしました。\nまずはステージを選択してください。",
            view=view_stage,
            ephemeral=True
        )
        
        # Viewの結果を待つ（ステージ未選択ならランダムになるロジックはEngineにあるが、ここでは選択を促す）
        await view_stage.wait()
        
        if view_stage.selected_stage_id:
            engine.stage_id = view_stage.selected_stage_id
            stage_name = get_stage_by_id(engine.stage_id).name
        else:
            # タイムアウト等
            default_stage = random.choice(STAGES)
            engine.stage_id = default_stage.id
            stage_name = f"{default_stage.name} (ランダム)"
            
        # 募集メッセージ（公開）
        view_join = JoinView()
        msg = await interaction.channel.send(
            f"⚔️ **Rumble Royale 参加者募集** ⚔️\n"
            f"開始時刻: {target_time.strftime('%H:%M')} (約{(target_time - now).seconds // 60}分後)\n"
            f"ステージ: {stage_name}\n"
            f"「参加する」ボタンを押してエントリーしてください！",
            view=view_join
        )
        engine.message_id = msg.id
        self._save_state()


async def setup(bot: commands.Bot):
    await bot.add_cog(Rumble(bot))
