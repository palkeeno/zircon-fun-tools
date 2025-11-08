"""Permission override helpers.

- Operators (config.OPERATOR_ROLE_ID) may always run any slash command.
- Non-operators can be granted per-command access by role via overrides stored in data/overrides.json, per guild.

Utilities here are dependency-light and safe to import from cogs.
"""
from __future__ import annotations

from typing import Dict, List, Optional
import os
import json
import logging

import discord

import config

_LOG = logging.getLogger(__name__)
_OVERRIDES_PATH = os.path.join("data", "overrides.json")

# 誰でも実行できるコマンド（権限チェックをスキップ）
PUBLIC_COMMANDS = {'poster', 'oracle', 'birthday'}


def _ensure_data_dir():
    os.makedirs("data", exist_ok=True)


def _load_overrides_raw() -> Dict:
    """Load raw overrides JSON. Returns a dict structure.

    Schema:
    {
      "guilds": {
        "<guild_id>": {
          "<command_name>": [<role_id>, ...]
        }
      }
    }
    """
    _ensure_data_dir()
    if not os.path.exists(_OVERRIDES_PATH):
        return {"guilds": {}}
    try:
        with open(_OVERRIDES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"guilds": {}}
            if "guilds" not in data or not isinstance(data["guilds"], dict):
                data["guilds"] = {}
            return data
    except Exception as e:
        _LOG.error("Failed to load overrides: %s", e)
        return {"guilds": {}}


def _save_overrides_raw(data: Dict) -> None:
    _ensure_data_dir()
    try:
        with open(_OVERRIDES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _LOG.error("Failed to save overrides: %s", e)


# Public helpers

def list_permitted_roles(guild_id: int, command_name: str) -> List[int]:
    data = _load_overrides_raw()
    g = data.get("guilds", {}).get(str(guild_id), {})
    roles = g.get(command_name, [])
    return [int(r) for r in roles]


def grant_permission(guild_id: int, command_name: str, role_id: int) -> None:
    data = _load_overrides_raw()
    g = data.setdefault("guilds", {}).setdefault(str(guild_id), {})
    lst = g.setdefault(command_name, [])
    if role_id not in lst:
        lst.append(role_id)
    _save_overrides_raw(data)


def revoke_permission(guild_id: int, command_name: str, role_id: int) -> None:
    data = _load_overrides_raw()
    g = data.setdefault("guilds", {}).setdefault(str(guild_id), {})
    lst = g.setdefault(command_name, [])
    if role_id in lst:
        lst.remove(role_id)
    # clean empty entries
    if not lst:
        g.pop(command_name, None)
    if not g:
        data.get("guilds", {}).pop(str(guild_id), None)
    _save_overrides_raw(data)


def list_all_permissions(guild_id: int) -> Dict[str, List[int]]:
    data = _load_overrides_raw()
    return data.get("guilds", {}).get(str(guild_id), {}).copy()


def is_operator_member(member: Optional[discord.Member]) -> bool:
    operator_role_id = getattr(config, "OPERATOR_ROLE_ID", 0)
    if not operator_role_id or not member:
        return False
    try:
        return any(r.id == operator_role_id for r in getattr(member, "roles", []))
    except Exception:
        return False


def can_run_command(interaction: discord.Interaction, command_name: str) -> bool:
    """Permission rule: operators may always run; others only if their guild role is permitted.

    - Public commands (poster, oracle) are accessible to everyone.
    - DMs: only operators (no roles to check).
    - Guild: return True if operator or has at least one permitted role for the command.
    """
    # パブリックコマンドは誰でも実行可能
    if command_name in PUBLIC_COMMANDS:
        return True
    
    member: Optional[discord.Member]
    if isinstance(interaction.user, discord.Member):
        member = interaction.user
    elif interaction.guild is not None:
        member = interaction.guild.get_member(interaction.user.id)
    else:
        member = None

    if is_operator_member(member):
        return True

    if interaction.guild is None or member is None:
        return False

    permitted = set(list_permitted_roles(interaction.guild.id, command_name))
    if not permitted:
        return False
    try:
        return any(r.id in permitted for r in member.roles)
    except Exception:
        return False
