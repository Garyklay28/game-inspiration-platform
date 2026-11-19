"""게임 별칭 사전 (기획안: '별칭 사전으로 한·중·영 표기 통일').

SUPABASE_URL / SUPABASE_KEY 가 설정되어 있으면 Supabase REST(PostgREST)에서 game_alias 테이블을 읽고,
없으면 data/alias_dictionary.json 을 쓴다. 두 구현은 같은 인터페이스(resolve / find_in_text)를 가진다.
테이블 정의는 supabase/schema.sql 참고.
"""
import json
import urllib.request
from typing import Dict, List, Optional

from .. import config


class AliasStore:
    def __init__(self, games: List[Dict]):
        self.games = games
        self._index = {}
        for g in games:
            for name in [g["zh"], g["ko"], g["en"]] + list(g.get("aliases", [])):
                self._index[name.lower()] = g

    @classmethod
    def load(cls) -> "AliasStore":
        if config.SUPABASE_URL and config.SUPABASE_KEY:
            return cls(_load_from_supabase())
        with open(config.DATA_DIR / "alias_dictionary.json", encoding="utf-8") as f:
            return cls(json.load(f)["games"])

    def resolve(self, name: str) -> Optional[Dict]:
        """임의 표기 → 표준 게임 레코드. 정확히 일치하는 별칭이 없으면 None."""
        if not name:
            return None
        return self._index.get(name.strip().lower())

    def resolve_id(self, game_id: str) -> Optional[Dict]:
        return next((g for g in self.games if g["game_id"] == game_id), None)

    def find_in_text(self, text: str) -> List[Dict]:
        """제목·키워드 안에 등장하는 게임을 모두 찾는다(긴 별칭 우선, 중복 제거)."""
        low = text.lower()
        found, seen = [], set()
        for alias in sorted(self._index, key=len, reverse=True):
            # 2글자 미만 영문 별칭(예: 'mc')은 오탐이 많아 단어 경계 확인
            if alias in low and (len(alias) > 2 or not alias.isascii() or _word_hit(low, alias)):
                g = self._index[alias]
                if g["game_id"] not in seen:
                    seen.add(g["game_id"])
                    found.append(g)
        return found


def _word_hit(text: str, word: str) -> bool:
    idx = text.find(word)
    while idx >= 0:
        before = text[idx - 1] if idx > 0 else " "
        after = text[idx + len(word)] if idx + len(word) < len(text) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        idx = text.find(word, idx + 1)
    return False


def _load_from_supabase() -> List[Dict]:
    url = config.SUPABASE_URL.rstrip("/") + "/rest/v1/game_alias?select=game_id,zh,ko,en,aliases"
    req = urllib.request.Request(url, headers={"apikey": config.SUPABASE_KEY,
                                               "Authorization": "Bearer " + config.SUPABASE_KEY})
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))
