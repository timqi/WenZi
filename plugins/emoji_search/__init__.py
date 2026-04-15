"""Emoji search plugin for WenZi launcher."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from wenzi.scripting.sources import fuzzy_match_fields

logger = logging.getLogger(__name__)

_MAX_RESULTS = 30
_MAX_GROUP_RESULTS = 200
_DATA_FILE = "emoji-tree.json"


def _load_emoji_data() -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]]]:
    """Load emoji-tree.json and return (records, group_map).

    *records* is a flat list of all emoji dicts.
    *group_map* maps lowercase group/subgroup names (en/zh) to the emoji list.
    """
    path = os.path.join(os.path.dirname(__file__), _DATA_FILE)
    if not os.path.isfile(path):
        logger.error("Emoji data file not found: %s", path)
        return [], {}

    try:
        with open(path, encoding="utf-8") as fh:
            tree = json.load(fh)
    except Exception:
        logger.exception("Failed to parse %s", path)
        return [], {}

    records: list[dict[str, str]] = []
    group_map: dict[str, list[dict[str, str]]] = {}

    for group in tree:
        group_en = group.get("name", "")
        group_zh = group.get("name_i18n", {}).get("zh_CN", "")
        group_emojis: list[dict[str, str]] = []

        for subgroup in group.get("list", []):
            subgroup_en = subgroup.get("name", "")
            subgroup_zh = subgroup.get("name_i18n", {}).get("zh_CN", "")
            subgroup_emojis: list[dict[str, str]] = []

            for entry in subgroup.get("list", []):
                name_i18n = entry.get("name_i18n", {})
                rec = {
                    "char": entry.get("char", ""),
                    "name_en": entry.get("name", ""),
                    "name_zh": name_i18n.get("zh_CN", ""),
                    "group_en": group_en,
                    "group_zh": group_zh,
                    "subgroup_en": subgroup_en,
                    "subgroup_zh": subgroup_zh,
                }
                records.append(rec)
                group_emojis.append(rec)
                subgroup_emojis.append(rec)

            if subgroup_en:
                group_map.setdefault(subgroup_en.lower(), []).extend(subgroup_emojis)
            if subgroup_zh:
                group_map.setdefault(subgroup_zh.lower(), []).extend(subgroup_emojis)

        if group_en:
            group_map.setdefault(group_en.lower(), []).extend(group_emojis)
        if group_zh:
            group_map.setdefault(group_zh.lower(), []).extend(group_emojis)

    return records, group_map


def _parse_query(
    query: str,
    group_map: dict[str, list[dict[str, str]]],
) -> tuple[str, str | None]:
    """Split *query* into (keyword, group_filter).

    Supports '@groupname' syntax. The text after '@' is consumed word-by-word
    from the end until a known group/subgroup name is matched (exact or fuzzy).
    This allows both 'cat @动物与自然' and '@face eye' (where 'face' is the
    group filter and 'eye' becomes the keyword).
    """
    from wenzi.scripting.sources import fuzzy_match as _fuzzy_match

    text = query.strip()
    if "@" not in text:
        return text, None

    at_index = text.rfind("@")
    before = text[:at_index].strip()
    after = text[at_index + 1 :].strip().lower()
    if not after:
        return before, None

    parts = after.split()
    for i in range(len(parts), 0, -1):
        candidate = " ".join(parts[:i])
        # Exact match
        if candidate in group_map:
            keyword = " ".join([before] + parts[i:]).strip()
            return keyword, candidate
        # Fuzzy match
        for key in group_map:
            matched, _ = _fuzzy_match(candidate, key)
            if matched:
                keyword = " ".join([before] + parts[i:]).strip()
                return keyword, candidate

    # Fallback: treat the whole after-@ text as the group filter.
    return before, after


def _search_emojis(
    query: str,
    records: list[dict[str, str]],
    group_map: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    """Return emoji records matching *query*.

    If the query contains '@groupname', the group name is fuzzy-matched
    against group/subgroup names (en/zh) to restrict the search pool.
    If no group matches, the search falls back to all records.
    Otherwise the keyword is fuzzy-matched across names and groups.
    """
    from wenzi.scripting.sources import fuzzy_match as _fuzzy_match

    q, group_filter = _parse_query(query, group_map)
    q = q.lower()
    if not q and not group_filter:
        return []

    # Determine the pool of records to search within.
    pool = records
    if group_filter:
        matched_groups: list[list[dict[str, str]]] = []
        for key, emojis in group_map.items():
            matched, _score = _fuzzy_match(group_filter, key)
            if matched:
                matched_groups.append(emojis)
        if matched_groups:
            seen: set[str] = set()
            pool = []
            for group in matched_groups:
                for rec in group:
                    if rec["char"] not in seen:
                        seen.add(rec["char"])
                        pool.append(rec)

    # 1. Group-only query: return the pooled group emojis.
    if not q:
        return pool[:_MAX_GROUP_RESULTS]

    # 2. Fuzzy match within the pool.
    # When a group filter is active, only match against emoji names to avoid
    # spurious hits on group metadata (e.g. "eye" matching "Smileys & Emotion").
    scored: list[tuple[int, dict[str, str]]] = []
    for rec in pool:
        if not rec["char"]:
            continue
        fields = (
            [rec["name_en"], rec["name_zh"]]
            if group_filter
            else [
                rec["name_en"],
                rec["name_zh"],
                rec["group_en"],
                rec["group_zh"],
                rec["subgroup_en"],
                rec["subgroup_zh"],
            ]
        )
        matched, score = fuzzy_match_fields(q, fields)
        if matched:
            scored.append((score, rec))

    scored.sort(key=lambda x: x[0], reverse=True)
    max_results = _MAX_GROUP_RESULTS if group_filter else _MAX_RESULTS
    return [rec for _, rec in scored[:max_results]]


def _copy_and_alert(wz, char: str) -> None:
    wz.pasteboard.set(char)
    wz.alert("Emoji copied", duration=1.2)


def _emoji_item(wz, rec: dict[str, str]) -> dict[str, Any]:
    char = rec["char"]
    subtitle = f"{rec['name_zh']} | {rec['name_en']} · {rec['group_zh']}"
    preview_html = (
        f"<div style='font-size:120px;text-align:center;padding-top:40px'>{char}</div>"
        f"<div style='text-align:center;color:#666;padding:10px 0 40px'>"
        f"{rec['name_zh']}<br>{rec['name_en']}<br>"
        f"{rec['group_zh']} / {rec['subgroup_zh']}"
        f"</div>"
    )
    return {
        "title": char,
        "subtitle": subtitle,
        "item_id": f"emoji:{char}",
        "action": lambda c=char: wz.type_text(c, method="paste"),
        "modifiers": {
            "alt": {
                "subtitle": "Copy to clipboard",
                "action": lambda c=char: _copy_and_alert(wz, c),
            }
        },
        "preview": {"type": "html", "content": preview_html},
    }


def setup(wz) -> None:
    """Register the emoji chooser source."""
    records, group_map = _load_emoji_data()

    @wz.chooser.source(
        "emoji_search",
        prefix="e",
        priority=5,
        description="Search and paste emoji (prefix: e)",
        show_preview=True,
        action_hints={"enter": "Paste emoji", "alt_enter": "Copy to clipboard"},
        universal_action=True,
    )
    def search(query: str) -> list[dict[str, Any]]:
        results = _search_emojis(query, records, group_map)
        return [_emoji_item(wz, rec) for rec in results]
