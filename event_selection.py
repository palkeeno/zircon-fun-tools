"""Winner-selection strategies, independent of Discord and persistence."""
from collections.abc import Callable, Mapping
from functools import partial
import random
from typing import Any

Event = Mapping[str, Any]
METHODS = {"random": "順次ランダム抽選", "majority": "多数派が勝利", "minority": "少数派が勝利"}


def _random_winners(event: Event) -> list[str]:
    people = list(event["entries"])
    if len(people) < event["count"]:
        raise ValueError("参加人数が抽選人数に足りません。受付を継続します。")
    return random.sample(people, event["count"])


def _vote_winners(event: Event, *, choose_size: Callable) -> list[str]:
    """Exclude zero votes and nonvoters; every tied option wins."""
    buckets = {}
    for uid, entry in event["entries"].items():
        vote = entry.get("vote")
        if vote is not None:
            buckets.setdefault(vote, []).append(uid)
    if not buckets:
        raise ValueError("投票がありません。受付を継続します。")
    target = choose_size(map(len, buckets.values()))
    return [uid for group in buckets.values() if len(group) == target for uid in group]


_STRATEGIES: dict[str, Callable[[Event], list[str]]] = {
    "random": _random_winners,
    "majority": partial(_vote_winners, choose_size=max),
    "minority": partial(_vote_winners, choose_size=min),
}


def select_winners(event: Event) -> list[str]:
    """Select once; the caller persists the result before announcing it."""
    try:
        strategy = _STRATEGIES[event["method"]]
    except KeyError as exc:
        raise ValueError("選出方式が不正です。イベント設定を確認してください。") from exc
    return strategy(event)
