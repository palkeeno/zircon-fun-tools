"""
じゃんけんゲームのコグ
このモジュールは、Discord上でじゃんけんゲームを実装します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
import traceback
import config

# ロギングの設定
logger = logging.getLogger(__name__)

class JankenView(discord.ui.View):
    """
    じゃんけんのUIを管理するクラス
    グー、チョキ、パーのボタンを提供します。
    """
    
    def __init__(self, game: 'Janken'):
        """
        じゃんけんのUIを初期化します。
        
        Args:
            game (Janken): じゃんけんゲームのインスタンス
        """
        super().__init__(timeout=30.0)
        self.game = game

    @discord.ui.button(label="グー", style=discord.ButtonStyle.primary, emoji="✊")
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        グーボタンが押されたときの処理
        """
        try:
            if not config.is_feature_enabled('janken'):
                await interaction.response.send_message("現在じゃんけん機能は無効化されています。", ephemeral=True)
                return
                
            await self.game.play(interaction, "rock")
        except Exception as e:
            logger.error(f"Error in rock button: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

    @discord.ui.button(label="チョキ", style=discord.ButtonStyle.primary, emoji="✌️")
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        チョキボタンが押されたときの処理
        """
        try:
            if not config.is_feature_enabled('janken'):
                await interaction.response.send_message("現在じゃんけん機能は無効化されています。", ephemeral=True)
                return
                
            await self.game.play(interaction, "scissors")
        except Exception as e:
            logger.error(f"Error in scissors button: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

    @discord.ui.button(label="パー", style=discord.ButtonStyle.primary, emoji="✋")
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        パーボタンが押されたときの処理
        """
        try:
            if not config.is_feature_enabled('janken'):
                await interaction.response.send_message("現在じゃんけん機能は無効化されています。", ephemeral=True)
                return
                
            await self.game.play(interaction, "paper")
        except Exception as e:
            logger.error(f"Error in paper button: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

class Janken(commands.Cog):
    """
    じゃんけんゲームのコグ
    じゃんけんゲームのコマンドと機能を提供します。
    """
    
    def __init__(self, bot: commands.Bot):
        """
        じゃんけんゲームのコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot

    @app_commands.command(
        name="janken",
        description="じゃんけんゲームを開始します"
    )
    async def janken(self, interaction: discord.Interaction):
        """
        じゃんけんゲームを開始します。
        
        Args:
            interaction (discord.Interaction): インタラクション
        """
        try:
            if not config.is_feature_enabled('janken'):
                await interaction.response.send_message("現在じゃんけん機能は無効化されています。", ephemeral=True)
                return
                
            view = JankenView(self)
            await interaction.response.send_message("じゃんけんを始めます！\nグー、チョキ、パーのいずれかを選んでください。", view=view)
        except Exception as e:
            logger.error(f"Error in janken command: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

    async def play(self, interaction: discord.Interaction, player_choice: str):
        """
        じゃんけんを実行します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            player_choice (str): プレイヤーの選択（rock/scissors/paper）
        """
        try:
            if not config.is_feature_enabled('janken'):
                await interaction.response.send_message("現在じゃんけん機能は無効化されています。", ephemeral=True)
                return
                
            bot_choice = random.choice(["rock", "scissors", "paper"])
            result = self.judge(player_choice, bot_choice)
            
            embed = discord.Embed(
                title="じゃんけんの結果",
                description=f"あなた: {config.JANKEN_EMOJIS[player_choice]}\n"
                          f"ボット: {config.JANKEN_EMOJIS[bot_choice]}\n\n"
                          f"結果: {result}",
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in play: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

    def judge(self, player: str, bot: str) -> str:
        """
        じゃんけんの勝敗を判定します。
        
        Args:
            player (str): プレイヤーの選択
            bot (str): ボットの選択
            
        Returns:
            str: 勝敗結果
        """
        if player == bot:
            return "引き分け！"
        elif (player == "rock" and bot == "scissors") or \
             (player == "scissors" and bot == "paper") or \
             (player == "paper" and bot == "rock"):
            return "あなたの勝ち！"
        else:
            return "ボットの勝ち！"

async def setup(bot: commands.Bot):
    """
    コグをボットに追加します。
    
    Args:
        bot (commands.Bot): ボットのインスタンス
    """
    try:
        await bot.add_cog(Janken(bot))
        logger.info("Janken cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Janken cog: {e}")
        logger.error(traceback.format_exc())
        raise 