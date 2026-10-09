"""Birthday validation and calendar ordering."""
import datetime


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError("誕生日はオブジェクトで指定してください")
    cid = row.get("character_id")
    if isinstance(cid, bool) or not isinstance(cid, (str, int)) or not str(cid).strip():
        raise ValueError("キャラクターIDが必要です")
    cid = str(cid).strip()
    if len(cid) > 100:
        raise ValueError("キャラクターIDは100文字以内で指定してください")
    name = row.get("name", "不明")
    if not isinstance(name, str) or not name.strip() or len(name) > 150:
        raise ValueError("名前は空でない150文字以内の文字列が必要です")
    for key in ("month", "day"):
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("月日は整数で指定してください")
    month, day = int(row["month"]), int(row["day"])
    datetime.date(2000, month, day)
    reported = row.get("reported", False)
    if not isinstance(reported, bool):
        raise ValueError("reportedは真偽値で指定してください")
    return {**row, "character_id": cid, "name": name.strip(), "month": month, "day": day, "reported": reported}


def next_date(record, today):
    for year in range(today.year, today.year + 9):
        try:
            candidate = datetime.date(year, record["month"], record["day"])
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    raise ValueError("次回の誕生日を計算できません")


def select(records, mode, today):
    if mode == "today":
        records = [b for b in records if (b["month"], b["day"]) == (today.month, today.day)]
    elif mode == "month":
        records = [b for b in records if b["month"] == today.month]
    if mode == "upcoming":
        return sorted(records, key=lambda b: (next_date(b, today), b["character_id"]))
    return sorted(records, key=lambda b: (b["month"], b["day"], b["character_id"]))
