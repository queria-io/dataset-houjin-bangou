"""国税庁 法人番号 データの取得 + dbt build パイプライン。

取得方式は2系統:
  full        前月末日時点の全件 zip (00_zenkoku_all_YYYYMMDD.zip, 約250MB) を公表サイトの
              ダウンロードページから取得し、raw を作り直す (--full-refresh)。月次・初回・コード push 時。
              全件は Web-API では取れない。
  incremental Web-API (webapi.py) の期間指定で、raw の max(_source_date) の翌日から前日までを
              1 日ずつ取得し、法人番号キーで raw に upsert する。あわせて変更履歴の過去分を
              少しずつ取り込む (raw_houjin_bangou_records にだけ足す):
                - 期間指定で 2015-12-01 から BACKFILL_END まで、1 回 HOUJIN_BACKFILL_DAYS 日ずつ
                - 商号変更の行があるのに最初の行 (処理区分 01) を持たない法人の変更履歴を、
                  法人番号指定 (history=1) で 1 回 HOUJIN_HISTORY_REQUESTS リクエストずつ

モードは環境変数 SYNC_MODE (full / incremental, 既定 full) で指定する。
incremental でも raw が存在しなければ full にフォールバックする (初回ビルド対策)。
incremental は Web-API のアプリケーション ID (HOUJIN_BANGOU_APP_ID) が要る。

fdl checkout の作業場の DuckLake カタログ (FDL_WORKING) に対して dbt build を実行する。
公開は fdl commit / fdl push が担う (scripts/build.sh)。incremental は公開済み raw との
差分判定を行うため、公開中のバージョンから始める (build-fdl.sh が fdl checkout する)。
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import httpx
from dbt.cli.main import dbtRunner

import webapi

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

ZENKEN_URL = "https://www.houjin-bangou.nta.go.jp/download/zenken/index.html"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TOKEN_FIELD = (
    "jp.go.nta.houjin_bangou.framework.web.common."
    "CNSFWTokenProcessor.request.token"
)
TOKEN_RE = re.compile(re.escape(TOKEN_FIELD) + r'"\s+value="([^"]+)"')
# 「CSV形式・Unicode」セクション (全件・差分とも同じ構造)
CSV_UNICODE_RE = re.compile(r'id="csv-unicode".*?id="xml-unicode"', re.DOTALL)
DO_DOWNLOAD_RE = re.compile(r"doDownload\((\d+)\)")
JST = timezone(timedelta(hours=9))
# 変更履歴を全件で始めた日 (raw_houjin_bangou_records の最初の全件 00_zenkoku_all_20261030)。
# 過去分の期間指定はこの日までを取る
BACKFILL_END = date(2026, 10, 30)



def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(60.0, read=600.0),
    )


def _filename_from_disposition(disposition: str | None) -> str | None:
    if not disposition:
        return None
    m = re.search(r"filename\*=[^']*'[^']*'([^;\s]+)", disposition)
    if m:
        return m.group(1)
    m = re.search(r'filename="?([^";]+)"?', disposition)
    return m.group(1) if m else None


def _zip_csv_url(zip_path: Path) -> str:
    """zip 内のCSV (.asc 等を除く) を特定し read_csv 用の zip:// URL を返す。"""
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csv_names:
        raise RuntimeError(f"zip 内に CSV が見つかりません: {zip_path}")
    return f"zip://{zip_path}/{csv_names[0]}"


def _post_download(client: httpx.Client, url: str, token: str, file_no: str, dest: Path) -> Path:
    resp = client.post(
        url,
        data={TOKEN_FIELD: token, "event": "download", "selDlFileNo": file_no},
    )
    resp.raise_for_status()
    filename = _filename_from_disposition(resp.headers.get("content-disposition"))
    out = dest / (filename or f"houjin_{file_no}.zip")
    out.write_bytes(resp.content)
    return out


def download_full(client: httpx.Client, dest_dir: Path) -> str:
    """全国版 zip をダウンロードし zip:// CSV URL を返す。"""
    logger.info("全件ダウンロードページを取得")
    page = client.get(ZENKEN_URL)
    page.raise_for_status()
    html = page.text

    token = TOKEN_RE.search(html).group(1)
    section = CSV_UNICODE_RE.search(html).group(0)
    file_no = DO_DOWNLOAD_RE.search(section).group(1)  # 全国版が先頭
    logger.info("全国版ファイル番号: %s", file_no)

    zip_path = _post_download(client, ZENKEN_URL, token, file_no, dest_dir)
    logger.info("全件DL完了: %s (%d bytes)", zip_path.name, zip_path.stat().st_size)
    return _zip_csv_url(zip_path)


@contextmanager
def _ducklake_connect(*, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection]:
    """fdl checkout の作業場の DuckLake をアタッチした新規 DuckDB セッションを開く。

    shared/scripts/build-fdl.sh が渡す環境変数 (作業場のカタログ ``FDL_WORKING`` と
    新しいデータファイルの置き場 ``FDL_DATA_PATH``) を使う。置き場が公開ストレージの
    ``data/`` のときは、build-fdl.sh が鍵を取り直す DuckDB の永続 secret を作っているので、
    この接続でも期限が切れるたびに取り直される。
    """
    catalog_path = os.environ["FDL_WORKING"]
    data_url = os.environ["FDL_DATA_PATH"]
    # ビルドが公開ストレージを読むときの名乗り。build-fdl.sh が queria-build として
    # 渡す。profiles.yml の config_options と同じ値を、こちらのセッションにも通す。
    # 接続を開くときにしか決められないので config= で渡す
    conn = duckdb.connect(
        ":memory:",
        config={"custom_user_agent": os.environ.get("QUERIA_USER_AGENT", "")},
    )
    try:
        conn.execute("INSTALL ducklake; LOAD ducklake;")
        conn.execute("INSTALL sqlite; LOAD sqlite;")
        conn.execute("INSTALL httpfs; LOAD httpfs;")
        # 永続 secret の credential_chain はこの拡張にある
        conn.execute("INSTALL aws; LOAD aws;")
        opts = (
            f"DATA_PATH '{data_url}', OVERRIDE_DATA_PATH true, "
            f"DATA_INLINING_ROW_LIMIT 0, META_TYPE 'sqlite', "
            f"META_JOURNAL_MODE 'WAL', BUSY_TIMEOUT 5000"
        )
        if read_only:
            opts += ", READ_ONLY"
        conn.execute(
            f"ATTACH 'ducklake:{catalog_path}' AS houjin_bangou ({opts})"
        )
        yield conn
    finally:
        conn.close()


def _max_source_date() -> date | None:
    """既存 raw_houjin_bangou の最大 _source_date を返す (無ければ None)。

    変更履歴を溜める raw_houjin_bangou_records が無いときも None を返す。

    fdl checkout した作業場のカタログ(=公開済みデータ)に対する読み取り専用の
    差分判定。raw が未作成 (初回ビルド等) なら None を返し full にフォールバック
    させる。
    """
    try:
        with _ducklake_connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT max(_source_date) FROM houjin_bangou.main.raw_houjin_bangou"
            ).fetchone()
            # 変更履歴は全件データを最初の行にするので、溜める表が無ければ全件から始める
            conn.execute(
                "SELECT 1 FROM houjin_bangou.main.raw_houjin_bangou_records LIMIT 1"
            )
            return row[0] if row and row[0] else None
    except duckdb.Error as e:
        logger.info(
            "raw_houjin_bangou か raw_houjin_bangou_records が未作成とみなす (%s)",
            e.__class__.__name__,
        )
        return None


def _backfill_after() -> date | None:
    """過去分の期間指定をどの日まで取り込んだか (まだなら None)。"""
    with _ducklake_connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT max(_source_date) FROM houjin_bangou.main.raw_houjin_bangou_records "
            "WHERE _source_date < ?",
            [BACKFILL_END],
        ).fetchone()
    return row[0] if row else None


def _history_targets(limit: int) -> list[str]:
    """商号変更か吸収合併の行があるのに、最初の行 (処理区分 01) を持たない法人。

    変更前の商号は、その法人の前の行からしか分からない。2015-12-01 より前に指定された
    法人は期間指定で最初の行を取れないので、法人番号指定で変更履歴をまとめて取る。
    """
    with _ducklake_connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT corporate_number FROM houjin_bangou.main.raw_houjin_bangou_records "
            "GROUP BY ALL "
            "HAVING bool_or(process IN ('11', '71')) AND NOT bool_or(process = '01') "
            "ORDER BY 1 LIMIT ?",
            [limit],
        ).fetchall()
    return [r[0] for r in rows]


def fetch_daily(client: httpx.Client, app_id: str, dest: Path, after: date) -> list[str]:
    """after の翌日から前日 (JST) までの差分を 1 日ずつ取る。当日分は更新中のことがあるので取らない。"""
    yesterday = datetime.now(JST).date() - timedelta(1)
    targets = webapi.days(after + timedelta(1), yesterday)
    logger.info("差分対象: %d 日分 (after=%s)", len(targets), after)
    written = [
        webapi.write_csv(dest, f"diff_{d:%Y%m%d}.csv", webapi.fetch_diff(client, app_id, d))
        for d in targets
    ]
    return [str(p) for p in written if p]


def fetch_backfill(client: httpx.Client, app_id: str, dest: Path, n_days: int) -> list[str]:
    """過去分の期間指定を、続きから n_days 日ぶん取る。"""
    done = _backfill_after()
    start = done + timedelta(1) if done else webapi.DIFF_START
    targets = webapi.days(start, min(start + timedelta(n_days - 1), BACKFILL_END))
    logger.info("過去分の期間指定: %d 日分 (%s から)", len(targets), start)
    written = [
        webapi.write_csv(dest, f"diff_{d:%Y%m%d}.csv", webapi.fetch_diff(client, app_id, d))
        for d in targets
    ]
    return [str(p) for p in written if p]


def fetch_histories(client: httpx.Client, app_id: str, dest: Path, n_requests: int) -> list[str]:
    """最初の行を持たない法人の変更履歴を、n_requests リクエストぶん取る。"""
    numbers = _history_targets(n_requests * webapi.NUM_BATCH)
    logger.info("法人番号指定の変更履歴: %d 法人", len(numbers))
    today = datetime.now(JST).date()
    written = [
        webapi.write_csv(
            dest, f"num_{today:%Y%m%d}_{i:05d}.csv", webapi.fetch_history(client, app_id, batch)
        )
        for i, batch in enumerate(webapi.chunks(numbers, webapi.NUM_BATCH))
    ]
    return [str(p) for p in written if p]


def _dbt(cmds: list[list[str]]) -> None:
    dbt = dbtRunner()
    for cmd in cmds:
        result = dbt.invoke(cmd)
        if not result.success:
            raise SystemExit(f"dbt {' '.join(cmd)} failed")


def main() -> None:
    target = os.environ.get("DBT_TARGET", sys.argv[1] if len(sys.argv) > 1 else "default")
    mode = (os.environ.get("SYNC_MODE") or "full").lower()

    after = _max_source_date() if mode == "incremental" else None
    if mode == "incremental" and after is None:
        logger.info("raw が存在しないため full にフォールバック")
        mode = "full"

    with tempfile.TemporaryDirectory(prefix="houjin_") as tmp, _client() as client:
        if mode == "incremental":
            app_id = os.environ["HOUJIN_BANGOU_APP_ID"]
            daily_dir, past_dir = Path(tmp, "daily"), Path(tmp, "past")
            daily_dir.mkdir()
            past_dir.mkdir()
            paths = fetch_daily(client, app_id, daily_dir, after)
            history_paths = fetch_backfill(
                client, app_id, past_dir, int(os.environ.get("HOUJIN_BACKFILL_DAYS", "300"))
            ) + fetch_histories(
                client, app_id, past_dir, int(os.environ.get("HOUJIN_HISTORY_REQUESTS", "1500"))
            )
            full_refresh = False
        else:
            paths = [download_full(client, Path(tmp))]
            history_paths = []
            full_refresh = True

        if not paths and not history_paths:
            logger.info("未取込の差分なし。ビルドをスキップ (already up to date)")
            return

        var_arg = json.dumps(
            {"houjin_csv_paths": paths, "houjin_history_csv_paths": history_paths}
        )
        build_cmd = ["build", "--target", target, "--vars", var_arg]
        if full_refresh:
            build_cmd.append("--full-refresh")
        # 過去分だけのときは、最新の行の raw_houjin_bangou を触らない
        if not paths:
            build_cmd += ["--select", "raw_houjin_bangou_records+"]

        _dbt([["deps"], build_cmd, ["docs", "generate", "--target", target, "--vars", var_arg]])


if __name__ == "__main__":
    main()
