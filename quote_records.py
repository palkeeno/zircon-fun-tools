"""Validation and identity-preserving quote imports, independent of Discord."""
import csv
import datetime
import io
import json
import uuid


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError("各名言はオブジェクトで指定してください")
    result = dict(row)
    for key, limit in [("speaker", 150), ("text", 4000)]:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f"{key} は空でない文字列（{limit}文字以内）が必要です")
        result[key] = value.strip()
    cid = row.get("character_id")
    if cid is not None and cid != "":
        if isinstance(cid, bool) or not isinstance(cid, (str, int)):
            raise ValueError("character_id は半角数字で指定してください")
        cid = str(cid).strip()
        if cid and (not cid.isascii() or not cid.isdigit() or len(cid) > 20):
            raise ValueError("character_id は20桁以内の半角数字で指定してください")
    result["character_id"] = cid or None
    identity = row.get("id")
    if identity is not None and (not isinstance(identity, str) or len(identity) > 100):
        raise ValueError("id は100文字以内の文字列で指定してください")
    result["id"] = (identity or "").strip()
    for key in ("created_at", "updated_at"):
        value = row.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"{key} はISO形式の日時で指定してください")
            try:
                datetime.datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{key} はISO形式の日時で指定してください") from exc
    if row.get("created_by") is not None and (isinstance(row["created_by"], bool) or not isinstance(row["created_by"], int)):
        raise ValueError("created_by は整数で指定してください")
    return result


def signature(row):
    return tuple(row.get(key) for key in ("speaker", "text", "character_id"))


def merge_records(rows, existing, actor_id, now):
    """Keep original creation metadata. Match explicit ID, then unique content."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("名言データは空でないリストで指定してください")
    by_id = {q.get("id"): q for q in existing if q.get("id")}
    by_content = {}
    for quote in existing:
        by_content.setdefault(signature(quote), []).append(quote)
    result, seen = [], set()
    for number, row in enumerate(rows, 1):
        try:
            item = normalize(row)
        except ValueError as exc:
            raise ValueError(f"{number}行目: {exc}") from exc
        previous = by_id.get(item["id"])
        if not item["id"]:
            candidates = by_content.get(signature(item), [])
            if len(candidates) > 1:
                raise ValueError(f"{number}行目: 同じ本文が複数あります。idを指定してください")
            previous = candidates[0] if candidates else None
        if previous:
            merged = {**previous, **item, "id": previous["id"]}
            for key in ("created_by", "created_at"):
                if key in previous:
                    merged[key] = previous[key]
                else:
                    merged.pop(key, None)
            merged["updated_at"] = previous.get("updated_at", now) if signature(item) == signature(previous) else now
        else:
            merged = {**item, "id": item["id"] or str(uuid.uuid4()),
                      "created_by": item.get("created_by", actor_id),
                      "created_at": item.get("created_at", now), "updated_at": item.get("updated_at", now)}
        if merged["id"] in seen:
            raise ValueError(f"{number}行目: 名言IDが重複しています")
        seen.add(merged["id"])
        result.append(merged)
    return result


def parse_upload(content, filename):
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("ファイルは5MB以内で指定してください")
    text = content.decode("utf-8-sig")
    if filename.lower().endswith(".json"):
        payload = json.loads(text)
        return payload.get("quotes") if isinstance(payload, dict) else payload
    if not filename.lower().endswith(".csv"):
        raise ValueError("対応形式はCSV/JSONです")
    rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    if not rows:
        return []
    headers = [cell.strip().lower() for cell in rows[0]]
    if "speaker" in headers or "text" in headers:
        if not {"speaker", "text"}.issubset(headers) or len(set(headers)) != len(headers):
            raise ValueError("CSVにはspeaker,textヘッダーが必要です（重複不可）")
        if any(len(row) != len(headers) for row in rows[1:]):
            raise ValueError("CSVの列数がヘッダーと一致しません")
        records = [dict(zip(headers, row)) for row in rows[1:]]
        for record in records:
            for field in ("created_by", "created_at", "updated_at"):
                if field in record and not record[field].strip():
                    record.pop(field)
            if "created_by" in record:
                record["created_by"] = int(record["created_by"])
        return records
    if any(len(row) not in (2, 3) for row in rows):
        raise ValueError("ヘッダーなしCSVはspeaker,text[,character_id]です")
    return [dict(zip(("speaker", "text", "character_id"), row)) for row in rows]
