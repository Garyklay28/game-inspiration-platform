"""공개 API(종합 인기·핫서치)를 한 번 호출해 오프라인 대체용 스냅샷을 저장한다.

  python -m scripts.save_snapshots

저장 위치: data/snapshots/popular_game_YYYYMMDD.json, trending_YYYYMMDD.json
(랭킹 API 는 봇 차단 대상이라 이 스크립트에서 호출하지 않는다. README 참고.)
"""
from datetime import datetime

from bili_agent.tools import bilibili_api


def main() -> None:
    day = datetime.now().strftime("%Y%m%d")
    popular = bilibili_api.fetch_popular_game_videos()
    if popular["origin"] != "live":
        raise SystemExit("실시간 수집 실패: %s" % popular.get("live_error"))
    print(bilibili_api.save_snapshot("popular_game_%s.json" % day, popular), len(popular["videos"]))
    trending = bilibili_api.fetch_trending_keywords()
    if trending["origin"] != "live":
        raise SystemExit("실시간 수집 실패: %s" % trending.get("live_error"))
    print(bilibili_api.save_snapshot("trending_%s.json" % day, trending), len(trending["keywords"]))


if __name__ == "__main__":
    main()
