"""国税庁 法人番号 全件データの取得 + dbt build + snapshot pipeline.

全件データは Web-API では取得できず、公表サイトのダウンロードページから
全国版 zip を POST で取得する。アプリID は不要。

手順:
  1. ダウンロードページ(GET)で cookie とトークン、全国版ファイル番号を取得
  2. 同一セッションで POST して 00_zenkoku_all_YYYYMMDD.zip (約250MB) を取得
  3. zip 内 CSV の zip:// パスを dbt の var(houjin_zip_url) として渡し build
  4. snapshot-to-r2 で Neon DuckLake を R2 のスタンドアロン DuckDB に書き出す

snapshot は dbt build と同一プロセスで実行する必要がある
(dataset-shared/README.md の制約を参照)。
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
from dbt.cli.main import dbtRunner

SHARED_SCRIPTS = Path(__file__).resolve().parent / "shared" / "scripts"
_spec = importlib.util.spec_from_file_location(
    "snapshot_to_r2", SHARED_SCRIPTS / "snapshot-to-r2.py"
)
assert _spec and _spec.loader
snapshot_to_r2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot_to_r2)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

DOWNLOAD_URL = "https://www.houjin-bangou.nta.go.jp/download/zenken/index.html"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TOKEN_FIELD = (
    "jp.go.nta.houjin_bangou.framework.web.common."
    "CNSFWTokenProcessor.request.token"
)
# ダウンロードページの「CSV形式・Unicode」セクションの最初の doDownload(...) が
# 全国版（00_zenkoku_all）。月次でファイル番号が変わるため動的に解決する。
TOKEN_RE = re.compile(
    re.escape(TOKEN_FIELD) + r'"\s+value="([^"]+)"'
)
CSV_UNICODE_RE = re.compile(
    r'id="csv-unicode".*?id="xml-unicode"', re.DOTALL
)
DO_DOWNLOAD_RE = re.compile(r"doDownload\((\d+)\)")


def _resolve_and_download(dest_dir: Path) -> Path:
    """全国版 zip をダウンロードしてローカルパスを返す。"""
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(60.0, read=600.0),
    ) as client:
        logger.info("ダウンロードページを取得: %s", DOWNLOAD_URL)
        page = client.get(DOWNLOAD_URL)
        page.raise_for_status()
        html = page.text

        token_match = TOKEN_RE.search(html)
        if not token_match:
            raise RuntimeError("トークンを抽出できませんでした")
        token = token_match.group(1)

        section = CSV_UNICODE_RE.search(html)
        if not section:
            raise RuntimeError("CSV形式・Unicode セクションを特定できませんでした")
        file_no_match = DO_DOWNLOAD_RE.search(section.group(0))
        if not file_no_match:
            raise RuntimeError("全国版ファイル番号を抽出できませんでした")
        file_no = file_no_match.group(1)
        logger.info("全国版ファイル番号: %s", file_no)

        logger.info("全国版 zip を POST でダウンロード中...")
        resp = client.post(
            DOWNLOAD_URL,
            data={
                TOKEN_FIELD: token,
                "event": "download",
                "selDlFileNo": file_no,
            },
        )
        resp.raise_for_status()

        filename = _filename_from_disposition(resp.headers.get("content-disposition"))
        zip_path = dest_dir / (filename or "00_zenkoku_all.zip")
        zip_path.write_bytes(resp.content)
        logger.info("ダウンロード完了: %s (%d bytes)", zip_path.name, zip_path.stat().st_size)
        return zip_path


def _filename_from_disposition(disposition: str | None) -> str | None:
    """content-disposition から filename を抽出する (RFC5987 / 通常形式)。"""
    if not disposition:
        return None
    # filename*=utf-8'jp'00_zenkoku_all_20260529.zip
    m = re.search(r"filename\*=[^']*'[^']*'([^;\s]+)", disposition)
    if m:
        return m.group(1)
    m = re.search(r'filename="?([^";]+)"?', disposition)
    return m.group(1) if m else None


def _zip_csv_url(zip_path: Path) -> str:
    """zip 内のCSV (.asc 等を除く) を特定し read_csv 用の zip:// URL を返す。"""
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csv_names:
        raise RuntimeError(f"zip 内に CSV が見つかりません: {zip_path}")
    if len(csv_names) > 1:
        logger.warning("zip 内に複数の CSV: %s (先頭を使用)", csv_names)
    return f"zip://{zip_path}/{csv_names[0]}"


def main() -> None:
    target = os.environ.get("DBT_TARGET", sys.argv[1] if len(sys.argv) > 1 else "default")

    # zip は数百MB あるため一時ディレクトリへ。build 完了まで保持する。
    with tempfile.TemporaryDirectory(prefix="houjin_") as tmp:
        zip_path = _resolve_and_download(Path(tmp))
        houjin_zip_url = _zip_csv_url(zip_path)
        logger.info("dbt var houjin_zip_url=%s", houjin_zip_url)

        # raw モデルが var('houjin_zip_url') を参照するため、build だけでなく
        # docs generate にも同じ var を渡す（未指定だとコンパイルエラーになる）。
        dbt_vars = f"{{houjin_zip_url: '{houjin_zip_url}'}}"
        dbt = dbtRunner()
        for cmd in (
            ["deps"],
            ["build", "--target", target, "--vars", dbt_vars],
            ["docs", "generate", "--target", target, "--vars", dbt_vars],
        ):
            result = dbt.invoke(cmd)
            if not result.success:
                raise SystemExit(f"dbt {' '.join(cmd)} failed")

    snapshot_to_r2.run(target)


if __name__ == "__main__":
    main()
