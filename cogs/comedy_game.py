"""
コメディゲームのコグ
このモジュールは、Discord上でキャット＆チョコレート風の大喜利ゲームを実装します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import json
import random
import asyncio
import config
import logging
import traceback

# ロギングの設定
logger = logging.getLogger(__name__)

class ComedyGame:
    """
    コメディゲームの状態を管理するクラス
    ゲームの進行状況やプレイヤーの情報を保持します。
    """
    
    def __init__(self):
        """
        コメディゲームを初期化します。
        """
        self.players = []
        self.situation = None
        self.cards = []
        self.answers = {}
        self.votes = {}
        self.vote_message = None
        self.is_voting = False

    def add_player(self, player: discord.Member) -> bool:
        """
        プレイヤーを追加します。
        
        Args:
            player (discord.Member): 追加するプレイヤー
            
        Returns:
            bool: 追加に成功したかどうか
        """
        if player not in self.players:
            self.players.append(player)
            return True
        return False

    def remove_player(self, player: discord.Member) -> bool:
        """
        プレイヤーを削除します。
        
        Args:
            player (discord.Member): 削除するプレイヤー
            
        Returns:
            bool: 削除に成功したかどうか
        """
        if player in self.players:
            self.players.remove(player)
            return True
        return False

    def get_player_count(self) -> int:
        """
        プレイヤー数を取得します。
        
        Returns:
            int: プレイヤー数
        """
        return len(self.players)

    def deal_cards(self, all_cards: dict):
        """
        カードを配ります。
        
        Args:
            all_cards (dict): 使用可能なカードのリスト
        """
        self.cards = random.sample(all_cards["cards"], 5)

    def add_answer(self, player: discord.Member, answer: str, used_cards: list):
        """
        回答を追加します。
        
        Args:
            player (discord.Member): 回答者
            answer (str): 回答内容
            used_cards (list): 使用したカード
        """
        self.answers[player] = {"answer": answer, "cards": used_cards}

    def add_vote(self, voter: discord.Member, is_ok: bool):
        """
        投票を追加します。
        
        Args:
            voter (discord.Member): 投票者
            is_ok (bool): OKかNGか
        """
        self.votes[voter] = is_ok

    def get_results(self) -> tuple:
        """
        投票結果を取得します。
        
        Returns:
            tuple: (OK票数, 総投票数)
        """
        if not self.votes:
            return None, 0, 0
        
        ok_count = sum(1 for is_ok in self.votes.values() if is_ok)
        total_votes = len(self.votes)
        return ok_count, total_votes

class VoteView(discord.ui.View):
    """
    投票用のUIを管理するクラス
    OK/NGボタンを提供します。
    """
    
    def __init__(self, game: ComedyGame):
        """
        投票用のUIを初期化します。
        
        Args:
            game (ComedyGame): ゲームのインスタンス
        """
        super().__init__(timeout=20.0)
        self.game = game

    @discord.ui.button(label="OK", style=discord.ButtonStyle.success)
    async def ok_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        OKボタンが押されたときの処理
        """
        try:
            if not config.is_feature_enabled('comedy'):
                await interaction.response.send_message("現在コメディゲーム機能は無効化されています。", ephemeral=True)
                return
                
            if self.game.is_voting:
                self.game.add_vote(interaction.user, True)
                await interaction.response.send_message("OKで投票しました！", ephemeral=True)
            else:
                await interaction.response.send_message("投票期間は終了しました。", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in OK button: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

    @discord.ui.button(label="NG", style=discord.ButtonStyle.danger)
    async def ng_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        NGボタンが押されたときの処理
        """
        try:
            if not config.is_feature_enabled('comedy'):
                await interaction.response.send_message("現在コメディゲーム機能は無効化されています。", ephemeral=True)
                return
                
            if self.game.is_voting:
                self.game.add_vote(interaction.user, False)
                await interaction.response.send_message("NGで投票しました！", ephemeral=True)
            else:
                await interaction.response.send_message("投票期間は終了しました。", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in NG button: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

    async def on_timeout(self):
        """
        タイムアウト時の処理
        """
        try:
            self.game.is_voting = False
            if self.game.vote_message:
                await self.game.vote_message.edit(view=None)
        except Exception as e:
            logger.error(f"Error in vote timeout: {e}")
            logger.error(traceback.format_exc())

class AnswerView(discord.ui.View):
    """
    回答用のUIを管理するクラス
    投票開始ボタンを提供します。
    """
    
    def __init__(self, game: ComedyGame, player: discord.Member):
        """
        回答用のUIを初期化します。
        
        Args:
            game (ComedyGame): ゲームのインスタンス
            player (discord.Member): 回答者
        """
        super().__init__(timeout=300.0)
        self.game = game
        self.player = player

    @discord.ui.button(label="投票開始", style=discord.ButtonStyle.primary)
    async def start_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        投票開始ボタンが押されたときの処理
        """
        try:
            if not config.is_feature_enabled('comedy'):
                await interaction.response.send_message("現在コメディゲーム機能は無効化されています。", ephemeral=True)
                return
                
            if interaction.user != self.player:
                await interaction.response.send_message("あなたは回答者ではありません！", ephemeral=True)
                return

            if self.player not in self.game.answers:
                await interaction.response.send_message("まず回答を提出してください！", ephemeral=True)
                return

            self.game.is_voting = True
            vote_view = VoteView(self.game)
            
            answer_data = self.game.answers[self.player]
            cards_text = ", ".join([card.get('item', card.get('skill', '不明')) for card in answer_data["cards"]])
            
            embed = discord.Embed(
                title="🎭 回答の投票",
                description=f"**回答者:** {self.player.display_name}\n\n"
                          f"**使用カード:** {cards_text}\n\n"
                          f"**回答:** {answer_data['answer']}\n\n"
                          "この回答はお題を解決できていますか？\n"
                          "20秒以内に投票してください！",
                color=discord.Color.blue()
            )
            
            self.game.vote_message = await interaction.channel.send(embed=embed, view=vote_view)
            await interaction.response.send_message("投票を開始しました！", ephemeral=True)

            try:
                await vote_view.wait()
                ok_count, total_votes = self.game.get_results()
                
                result_embed = discord.Embed(
                    title="🎭 投票結果",
                    description=f"**回答者:** {self.player.display_name}\n\n"
                              f"**OK票:** {ok_count}\n"
                              f"**NG票:** {total_votes - ok_count}\n"
                              f"**総投票数:** {total_votes}\n\n"
                              f"**判定:** {'解決成功！' if ok_count > total_votes - ok_count else '解決失敗...'}",
                    color=discord.Color.green() if ok_count > total_votes - ok_count else discord.Color.red()
                )
                
                await self.game.vote_message.edit(embed=result_embed, view=None)
                
            except Exception as e:
                logger.error(f"Error in vote process: {e}")
                logger.error(traceback.format_exc())
                await interaction.channel.send(f"❌ エラーが発生しました: {str(e)}")
        except Exception as e:
            logger.error(f"Error in start_vote: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

class Comedy(commands.Cog):
    """
    コメディゲームのコグ
    大喜利ゲームのコマンドと機能を提供します。
    """
    
    def __init__(self, bot: commands.Bot):
        """
        コメディゲームのコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot
        self.games = {}
        self.load_data()

    def load_data(self):
        """
        ゲームデータを読み込みます。
        """
        try:
            with open("data/situations.json", "r", encoding="utf-8") as f:
                self.situations = json.load(f)
            with open("data/solution_cards.json", "r", encoding="utf-8") as f:
                self.cards = json.load(f)
        except Exception as e:
            logger.error(f"Error loading game data: {e}")
            logger.error(traceback.format_exc())
            raise

    @app_commands.command(
        name="comedy",
        description="キャット＆チョコレート風の大喜利ゲームを開始します"
    )
    async def comedy(self, interaction: discord.Interaction):
        """
        大喜利ゲームを開始します。
        
        Args:
            interaction (discord.Interaction): インタラクション
        """
        try:
            if not config.is_feature_enabled('comedy'):
                await interaction.response.send_message("現在コメディゲーム機能は無効化されています。", ephemeral=True)
                return
                
            channel_id = interaction.channel_id
            
            if channel_id in self.games:
                await interaction.response.send_message("このチャンネルではすでにゲームが進行中です！", ephemeral=True)
                return

            game = ComedyGame()
            self.games[channel_id] = game

            # お題を選択
            situation = random.choice(self.situations["situations"])
            game.situation = situation
            game.deal_cards(self.cards)

            # お題と手札を表示
            cards_text = "\n".join([f"- {card.get('item', card.get('skill', '不明'))}" for card in game.cards])
            embed = discord.Embed(
                title="🎭 お題発表！",
                description=f"**お題:**\n{situation['description']}\n\n"
                          f"**手札:**\n{cards_text}\n\n"
                          "手札から1〜3枚のカードを使って、状況を解決する方法を考えてください！\n"
                          "回答するには `/answer` コマンドを使用してください。",
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in comedy command: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

    @app_commands.command(
        name="answer",
        description="お題に対する回答を提出します"
    )
    @app_commands.describe(
        card_count="使用するカードの数（1-3）",
        answer="あなたの解決策"
    )
    async def answer(self, interaction: discord.Interaction, card_count: int, answer: str):
        """
        お題に対する回答を提出します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            card_count (int): 使用するカードの数
            answer (str): 解決策
        """
        try:
            if not config.is_feature_enabled('comedy'):
                await interaction.response.send_message("現在コメディゲーム機能は無効化されています。", ephemeral=True)
                return
                
            channel_id = interaction.channel_id
            
            if channel_id not in self.games:
                await interaction.response.send_message("このチャンネルではゲームが進行していません！", ephemeral=True)
                return

            game = self.games[channel_id]
            
            if not 1 <= card_count <= 3:
                await interaction.response.send_message("カードの数は1〜3枚の間で指定してください！", ephemeral=True)
                return

            # カードを選択
            used_cards = random.sample(game.cards, card_count)
            game.add_answer(interaction.user, answer, used_cards)

            # 回答を表示
            cards_text = ", ".join([card.get('item', card.get('skill', '不明')) for card in used_cards])
            embed = discord.Embed(
                title="🎭 回答提出",
                description=f"**回答者:** {interaction.user.display_name}\n\n"
                          f"**使用カード:** {cards_text}\n\n"
                          f"**回答:** {answer}",
                color=discord.Color.green()
            )
            
            view = AnswerView(game, interaction.user)
            await interaction.response.send_message(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error in answer command: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

async def setup(bot: commands.Bot):
    """
    コグをボットに追加します。
    
    Args:
        bot (commands.Bot): ボットのインスタンス
    """
    try:
        await bot.add_cog(Comedy(bot))
        logger.info("Comedy cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Comedy cog: {e}")
        logger.error(traceback.format_exc())
        raise 