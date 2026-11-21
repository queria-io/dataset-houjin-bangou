"""国税庁 法人番号システム Web-API (Ver.4) の取得。

使う機能は 2 つ:
  diff  取得期間を指定して情報を取得する (2015-12-01 以降、1 日ずつ取る)
  num   法人番号を指定して情報を取得する (history=1 で変更履歴も、1 回 10 件まで)

応答形式は CSV・Unicode (type=02)。1 行目はヘッダー (最終更新年月日,総件数,分割番号,分割数)、
2 行目以降は全件・差分のダウンロードと同じ 30 列。2,000 件を超えると分割され、分割番号を
上げて分割数まで取り直す。

アプリケーション ID は環境変数 HOUJIN_BANGOU_APP_ID から読む。
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx

API_URL = "https://api.houjin-bangou.nta.go.jp/4"
# 取得期間を指定する機能が受け付ける最初の日 (これより前はエラーコード 013)
DIFF_START = date(2015, 12, 1)
# 法人番号を指定する機能に 1 回で渡せる件数
NUM_BATCH = 10


@dataclass(frozen=True)
class Page:
    total: int
    divide_number: int
    divide_size: int
    body: str  # ヘッダーを除いたデータ行 (末尾改行つき、0 件なら空)


def parse_page(text: str) -> Page:
    """応答の 1 ページをヘッダーとデータ行に分ける。"""
    header, _, body = text.lstrip("﻿").partition("\n")
    _, total, number, size = header.strip().split(",")
    return Page(int(total), int(number), int(size), body)


def _get(client: httpx.Client, path: str, params: dict[str, str], wait: float) -> Page:
    resp = client.get(f"{API_URL}/{path}", params={**params, "type": "02"})
    resp.raise_for_status()
    # 1 リクエストごとに間を空ける (短い間隔で多数送るとアクセス制限される)
    time.sleep(wait)
    return parse_page(resp.text)


def _pages(
    client: httpx.Client, path: str, params: dict[str, str], wait: float
) -> Iterator[Page]:
    first = _get(client, path, {**params, "divide": "1"}, wait)
    yield first
    for n in range(2, first.divide_size + 1):
        yield _get(client, path, {**params, "divide": str(n)}, wait)


def fetch_diff(client: httpx.Client, app_id: str, day: date, wait: float = 1.0) -> str:
    """day に更新された法人の行を、ダウンロードの差分と同じ CSV (ヘッダーなし) で返す。"""
    params = {"id": app_id, "from": day.isoformat(), "to": day.isoformat()}
    return "".join(p.body for p in _pages(client, "diff", params, wait))


def fetch_history(
    client: httpx.Client, app_id: str, numbers: Sequence[str], wait: float = 1.0
) -> str:
    """法人番号ごとの変更履歴をすべて (latest=0 の行も) CSV (ヘッダーなし) で返す。"""
    if not 0 < len(numbers) <= NUM_BATCH:
        raise ValueError(f"法人番号は 1〜{NUM_BATCH} 件で渡す: {len(numbers)} 件")
    params = {"id": app_id, "number": ",".join(numbers), "history": "1"}
    return "".join(p.body for p in _pages(client, "num", params, wait))


def days(start: date, end: date) -> list[date]:
    """start から end まで (両端を含む) の日付。"""
    return [start + timedelta(n) for n in range((end - start).days + 1)]


def chunks(items: Sequence[str], size: int) -> list[Sequence[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def write_csv(dest: Path, name: str, body: str) -> Path | None:
    """データ行があれば dest/name に書いてパスを返す (0 件なら書かない)。"""
    if not body:
        return None
    path = dest / name
    path.write_text(body, encoding="utf-8")
    return path
