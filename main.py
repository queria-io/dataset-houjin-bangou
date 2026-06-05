"""国税庁 法人番号 データの取得 + dbt build + snapshot pipeline.

取得方式は2系統:
  full        前月末日時点の全件 zip (00_zenkoku_all_YYYYMMDD.zip, 約250MB) を取得し
              raw を作り直す (--full-refresh)。月次・初回・コード push 時。
  incremental 日次の差分 zip (diff_YYYYMMDD.zip) のうち未取込分のみ取得し、法人番号キーで
              raw に upsert する。raw の max(_source_date) より新しい日付の差分だけ落とす。

いずれも Web-API ではなく公表サイトのダウンロードページに POST して取得する
(アプリID 不要)。差分は約40日しか保持されないため、全件をベースに差分を重ねる。

モードは環境変数 HOUJIN_MODE (full / incremental, 既定 full) で指定する。
incremental でも raw が存在しなければ full にフォールバックする (初回ビルド対策)。

snapshot は dbt build と同一プロセスで実行する必要がある
(dataset-shared/README.md の制約を参照)。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

import duckdb
import httpx
from dbt.cli.main import dbtRunner

SHARED_SCRIPTS = Path(__file__).resolve().parent / "shared" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))
from queria_config import load_target  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "snapshot_to_r2", SHARED_SCRIPTS / "snapshot-to-r2.py"
)
assert _spec and _spec.loader
snapshot_to_r2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot_to_r2)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

ZENKEN_URL = "https://www.houjin-bangou.nta.go.jp/download/zenken/index.html"
SABUN_URL = "https://www.houjin-bangou.nta.go.jp/download/sabun/"
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
# 差分行: 令和N年M月D日 ... doDownload(番号)
DIFF_ROW_RE = re.compile(r"令和(\d+)年(\d+)月(\d+)日.*?doDownload\((\d+)\)", re.DOTALL)


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


def list_diff_files(html: str) -> list[tuple[date, str]]:
    """差分ページの「CSV形式・Unicode」から (日付, ファイル番号) を新しい順で返す。"""
    section = CSV_UNICODE_RE.search(html).group(0)
    pairs: list[tuple[date, str]] = []
    for m in DIFF_ROW_RE.finditer(section):
        y = 2018 + int(m.group(1))  # 令和N年 → 西暦
        d = date(y, int(m.group(2)), int(m.group(3)))
        pairs.append((d, m.group(4)))
    return pairs


def download_diffs(client: httpx.Client, dest_dir: Path, after: date | None) -> list[str]:
    """after より新しい日付の差分 zip を取得し zip:// CSV URL のリストを返す。"""
    page = client.get(SABUN_URL)
    page.raise_for_status()
    html = page.text
    token = TOKEN_RE.search(html).group(1)

    pairs = list_diff_files(html)
    if not pairs:
        raise RuntimeError("差分ファイルを1件も抽出できませんでした")
    oldest = min(d for d, _ in pairs)
    if after is not None and after < oldest:
        logger.warning(
            "未取込日 %s が差分の保持範囲(最古 %s)より古い。全件フルリフレッシュが必要",
            after,
            oldest,
        )

    targets = [(d, no) for d, no in pairs if after is None or d > after]
    targets.sort()  # 古い順に取り込む
    logger.info("差分対象: %d 日分 (after=%s)", len(targets), after)

    urls: list[str] = []
    for d, no in targets:
        zip_path = _post_download(client, SABUN_URL, token, no, dest_dir)
        logger.info("差分DL %s: %s (%d bytes)", d, zip_path.name, zip_path.stat().st_size)
        urls.append(_zip_csv_url(zip_path))
    return urls


def _max_source_date(target_name: str) -> date | None:
    """既存 raw_houjin_bangou の最大 _source_date を返す (無ければ None)。"""
    target = load_target(target_name)
    conn = duckdb.connect(":memory:")
    try:
        conn.execute("INSTALL ducklake; LOAD ducklake;")
        conn.execute("INSTALL postgres; LOAD postgres;")
        conn.execute("INSTALL httpfs; LOAD httpfs;")
        conn.execute(
            "CREATE SECRET r2 (TYPE r2, KEY_ID ?, SECRET ?, ACCOUNT_ID ?)",
            [target.s3_access_key_id, target.s3_secret_access_key, target.cf_account_id],
        )
        conn.execute(
            f"ATTACH '{target.ducklake_uri}' AS \"{target.dataset}\" "
            f"(DATA_PATH '{target.data_path}', META_SCHEMA '{target.meta_schema}', READ_ONLY)"
        )
        row = conn.execute(
            f'SELECT max(_source_date) FROM "{target.dataset}".main.raw_houjin_bangou'
        ).fetchone()
        return row[0] if row and row[0] else None
    except duckdb.Error as e:
        logger.info("raw_houjin_bangou 未作成とみなす (%s)", e.__class__.__name__)
        return None
    finally:
        conn.close()


def main() -> None:
    target = os.environ.get("DBT_TARGET", sys.argv[1] if len(sys.argv) > 1 else "default")
    mode = os.environ.get("HOUJIN_MODE", "full").lower()

    after = _max_source_date(target) if mode == "incremental" else None
    if mode == "incremental" and after is None:
        logger.info("raw が存在しないため full にフォールバック")
        mode = "full"

    with tempfile.TemporaryDirectory(prefix="houjin_") as tmp, _client() as client:
        if mode == "incremental":
            paths = download_diffs(client, Path(tmp), after)
            if not paths:
                logger.info("未取込の差分なし。ビルドをスキップ (already up to date)")
                return
            full_refresh = False
        else:
            paths = [download_full(client, Path(tmp))]
            full_refresh = True

        var_arg = f"{{houjin_csv_paths: {json.dumps(paths)}}}"
        build_cmd = ["build", "--target", target, "--vars", var_arg]
        if full_refresh:
            build_cmd.append("--full-refresh")

        dbt = dbtRunner()
        for cmd in (
            ["deps"],
            build_cmd,
            ["docs", "generate", "--target", target, "--vars", var_arg],
        ):
            result = dbt.invoke(cmd)
            if not result.success:
                raise SystemExit(f"dbt {' '.join(cmd)} failed")

    snapshot_to_r2.run(target)


if __name__ == "__main__":
    main()
