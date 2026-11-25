"""공유 작업 공간(블랙보드).

원시 데이터(수백 개 영상)는 LLM 대화에 그대로 넣지 않고 여기에 보관한다.
각 에이전트는 도구를 통해 필요한 요약만 꺼내 본다 → 토큰 절약 + 숫자 환각 방지.
에이전트 사이의 결과 전달도 이 작업 공간을 거친다(수직 구조: 에이전트끼리 직접 대화하지 않음).
"""
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .contracts import BiliTask
from .tools.alias_store import AliasStore


class Workspace:
    def __init__(self, task: BiliTask, alias_store: AliasStore):
        self.task = task
        self.alias = alias_store
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.requested_game: Optional[Dict] = None
        if task.game:
            self.requested_game = alias_store.resolve(task.game) or next(
                iter(alias_store.find_in_text(task.game)), None)
        # 1 수집 결과
        self.raw_videos: List[Dict] = []
        self.keywords: List[Dict] = []
        self.aside_events: List[Dict] = []
        # 2 정규화 결과 (게임 영상만, game_ids 부착)
        self.videos: List[Dict] = []
        self.normalized = False
        self.data_sources: List[Dict] = []
        self.warnings: List[str] = []
        self.findings: Dict[str, Dict] = {}  # 에이전트 이름 → 제출 결과
        self.cache: Dict[str, Any] = {}  # 결정적 계산 결과(보고서·DB 행 조립용)
        self.trace: List[Dict] = []
        self._t0 = time.time()

    # ── 데이터 ──
    @property
    def collected(self) -> bool:
        return bool(self.raw_videos)

    def add_raw(self, videos: List[Dict]) -> int:
        seen = {v["bvid"] for v in self.raw_videos}
        new = [v for v in videos if v["bvid"] not in seen]
        self.raw_videos.extend(new)
        return len(new)

    def videos_for(self, game_id: Optional[str] = None) -> List[Dict]:
        pool = self.videos if self.normalized else self.raw_videos
        if not game_id:
            return pool
        return [v for v in pool if game_id in (v.get("game_ids") or
                                                [g["game_id"] for g in self.alias.find_in_text(v["title"])])]

    def add_source(self, name: str, meta: Dict) -> None:
        row = {"name": name}
        row.update({k: meta[k] for k in ("origin", "endpoint", "fetched_at", "snapshot_file", "live_error", "file",
                                          "age_h", "encoding") if meta.get(k) is not None})
        self.data_sources.append(row)
        if meta.get("origin") == "snapshot":
            self.warnings.append("%s: 실시간 수집 실패로 스냅샷(%s) 사용" % (name, meta.get("snapshot_file")))

    # ── 실행 기록 ──
    def log(self, agent: str, event: str, detail: str = "", ok: bool = True) -> Dict:
        row = {"t": round(time.time() - self._t0, 1), "agent": agent, "event": event,
               "detail": detail[:160], "ok": ok}
        self.trace.append(row)
        return row
