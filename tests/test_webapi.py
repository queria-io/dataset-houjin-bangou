from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

import webapi

ROW = '{n},1010001000001,12,0,2019-04-03,2019-04-01,"株式会社テスト",,301,"東京都","千代田区","霞が関",,13,101,1000000,,,,,,,2015-10-05,1,,,,,,0\n'


def _page(total: int, number: int, size: int, rows: int) -> str:
    return f"2019-04-03,{total},{number},{size}\n" + "".join(ROW.format(n=i) for i in range(rows))


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_page_splits_header_and_rows():
    page = webapi.parse_page("﻿" + _page(2, 1, 1, 2))
    assert (page.total, page.divide_number, page.divide_size) == (2, 1, 1)
    assert page.body.count("\n") == 2


def test_parse_page_without_rows():
    assert webapi.parse_page("2019-04-03,0,1,1\n").body == ""


def test_fetch_diff_follows_divide():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        q = parse_qs(request.url.query.decode())
        seen.append(q)
        n = int(q["divide"][0])
        return httpx.Response(200, text=_page(5, n, 3, 2 if n < 3 else 1))

    body = webapi.fetch_diff(_client(handler), "APPID", date(2019, 4, 3), wait=0)
    assert body.count("\n") == 5
    assert [q["divide"][0] for q in seen] == ["1", "2", "3"]
    assert seen[0]["from"] == seen[0]["to"] == ["2019-04-03"]
    assert seen[0]["type"] == ["02"]
    assert seen[0]["id"] == ["APPID"]


def test_fetch_history_sends_numbers_with_history():
    def handler(request: httpx.Request) -> httpx.Response:
        q = parse_qs(request.url.query.decode())
        assert request.url.path == "/4/num"
        assert q["number"] == ["1,2"]
        assert q["history"] == ["1"]
        return httpx.Response(200, text=_page(1, 1, 1, 1))

    assert webapi.fetch_history(_client(handler), "APPID", ["1", "2"], wait=0)


def test_fetch_history_rejects_more_than_ten():
    with pytest.raises(ValueError):
        webapi.fetch_history(_client(lambda r: httpx.Response(200)), "x", [str(i) for i in range(11)])


def test_http_error_raises():
    with pytest.raises(httpx.HTTPStatusError):
        webapi.fetch_diff(_client(lambda r: httpx.Response(403, text="error")), "x", date(2019, 4, 3), wait=0)


def test_days_and_chunks():
    assert webapi.days(date(2026, 1, 30), date(2026, 2, 1)) == [
        date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1)
    ]
    assert webapi.days(date(2026, 2, 2), date(2026, 2, 1)) == []
    assert [list(c) for c in webapi.chunks([str(i) for i in range(12)], 10)] == [
        [str(i) for i in range(10)], ["10", "11"]
    ]


def test_write_csv_skips_empty(tmp_path):
    assert webapi.write_csv(tmp_path, "a.csv", "") is None
    assert webapi.write_csv(tmp_path, "b.csv", "x\n").read_text() == "x\n"
