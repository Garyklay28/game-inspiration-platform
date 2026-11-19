"""공유 작업 공간(블랙보드).

원시 데이터(수백 개 영상 JSON)는 LLM 대화에 그대로 넣지 않고 여기에 보관한다.
워커는 도구를 통해 '필요한 요약'만 꺼내 본다 → 토큰 절약 + 숫자 환각 방지.
"""
import time
from typing import Any, Dict, List, Optional

from .contracts import BiliTask
from .tools.alias_store import AliasStore


class Workspace:
    def __init__(self, task: BiliTask, alias_store: AliasStore):
        self.task = task
        self.alias = alias_store
        self.requested_game: Optional[Dict] = None
        if task.game:
            self.requested_game = alias_store.resolve(task.game) or next(
                iter(alias_store.find_in_text(task.game)), None)
        self.videos: List[Dict] = []
        self.keywords: List[Dict] = []
        self.data_sources: List[Dict] = []
        self.warnings: List[str] = []
        self.findings: Dict[str, Dict] = {}  # 워커 이름 → submit_findings 입력
        self.cache: Dict[str, Any] = {}  # 도구가 계산한 결정적 결과(보고서 조립용)
        self.trace: List[Dict] = []
        self._t0 = time.time()

    # ── 데이터 ──
    @property
    def collected(self) -> bool:
        return bool(self.videos)

    def add_videos(self, videos: List[Dict]) -> int:
        seen = {v["bvid"] for v in self.videos}
        new = [v for v in videos if v["bvid"] not in seen]
        self.videos.extend(new)
        return len(new)

    def videos_for(self, game_id: Optional[str] = None) -> List[Dict]:
        if not game_id:
            return self.videos
        return [v for v in self.videos
                if any(g["game_id"] == game_id for g in self.alias.find_in_text(v["title"]))]

    def add_source(self, name: str, meta: Dict) -> None:
        row = {"name": name}
        row.update({k: meta[k] for k in ("origin", "endpoint", "fetched_at", "snapshot_file", "live_error")
                    if meta.get(k)})
        self.data_sources.append(row)
        if meta.get("origin") == "snapshot":
            self.warnings.append("%s: 실시간 수집 실패로 스냅샷(%s) 사용" % (name, meta.get("snapshot_file")))

    # ── 실행 기록 ──
    def log(self, agent: str, event: str, detail: str = "", ok: bool = True) -> Dict:
        row = {"t": round(time.time() - self._t0, 1), "agent": agent, "event": event,
               "detail": detail[:160], "ok": ok}
        self.trace.append(row)
        return row
