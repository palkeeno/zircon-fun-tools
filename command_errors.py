"""One error response path for slash commands and component callbacks."""
import logging
import discord
from discord import app_commands

logger = logging.getLogger(__name__)


async def send_error(interaction, error):
    cause = getattr(error, "original", error)
    if isinstance(cause, app_commands.MissingPermissions):
        message = "この操作に必要な権限がありません。管理者に確認してください。"
    elif isinstance(cause, app_commands.BotMissingPermissions):
        message = "Botに必要な権限がありません。管理者に確認してください。"
    elif isinstance(cause, app_commands.NoPrivateMessage):
        message = "このコマンドはサーバー内で実行してください。"
    elif isinstance(cause, app_commands.CommandOnCooldown):
        message = f"あと{cause.retry_after:.0f}秒待ってから実行してください。"
    elif isinstance(cause, ValueError):
        message = str(cause)[:1500]
    else:
        logger.error("Command failed: %s", getattr(interaction, "command", None),
                     exc_info=(type(cause), cause, cause.__traceback__))
        message = "処理中にエラーが発生しました。管理者にお問い合わせください。"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        else:
            await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.exception("Could not send error response")
