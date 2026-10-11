"""The HTTP client: caching, pacing, retries, faults, and the session's memory."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from gov_gazetteer_mcp import __version__
from gov_gazetteer_mcp.client import ENDPOINT, GovError, user_agent

from .conftest import NIKOLAUSBERG, make_http, recorded

GET_NIKOLAUSBERG = ("getObject", [("itemId", NIKOLAUSBERG)])


def fault(status: int = 500, text: str = 'For input string: "x"') -> httpx.Response:
    body = (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        f"<soap:Fault><faultcode>soap:Server</faultcode><faultstring>{text}</faultstring>"
        "</soap:Fault></soap:Body></soap:Envelope>"
    )
    return httpx.Response(status, text=body)


@pytest.fixture
def router():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as r:
        yield r


async def test_the_user_agent_names_the_project_and_the_contact(router, tmp_path):
    route = router.post(ENDPOINT).mock(return_value=recorded("getObject__NIKERG-W3401.xml"))
    http = make_http(tmp_path, contact="me@example.org")
    await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    sent = route.calls[0].request
    assert sent.headers["user-agent"] == (
        f"gov-gazetteer-mcp/{__version__} "
        "(+https://github.com/ianderso/gov-gazetteer-mcp; me@example.org)"
    )
    assert sent.headers["content-type"].startswith("text/xml")
    assert (
        user_agent()
        == f"gov-gazetteer-mcp/{__version__} (+https://github.com/ianderso/gov-gazetteer-mcp)"
    )


async def test_answers_are_cached_on_disk_and_reused(router, tmp_path):
    route = router.post(ENDPOINT).mock(return_value=recorded("getObject__NIKERG-W3401.xml"))
    first = make_http(tmp_path)
    obj, _ = await first.call(*GET_NIKOLAUSBERG, ttl_days=30)
    second = make_http(tmp_path)  # a new session, the same cache
    again, _ = await second.call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert again == obj and route.call_count == 1 and second.cache_hits == 1


async def test_refresh_asks_again(router, http):
    route = router.post(ENDPOINT).mock(return_value=recorded("getObject__NIKERG-W3401.xml"))
    await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    await http.call(*GET_NIKOLAUSBERG, ttl_days=30, refresh=True)
    assert route.call_count == 2


async def test_an_expired_or_unreadable_entry_is_fetched_again(router, tmp_path):
    route = router.post(ENDPOINT).mock(return_value=recorded("getObject__NIKERG-W3401.xml"))
    http = make_http(tmp_path)
    await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    for entry in (tmp_path / "cache").glob("*.json"):
        entry.write_text("{truncated")
    await make_http(tmp_path).call(*GET_NIKOLAUSBERG, ttl_days=30)
    for entry in (tmp_path / "cache").glob("*.json"):
        data = json.loads(entry.read_text())
        entry.write_text(json.dumps({**data, "stored": data["stored"] - 31 * 86400}))
    await make_http(tmp_path).call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert route.call_count == 3


async def test_objects_an_answer_carried_are_not_asked_for_again(router, http):
    route = router.post(ENDPOINT).mock(return_value=recorded("searchByName__Quedlinburg.xml"))
    await http.call("searchByName", [("placename", "Quedlinburg")], ttl_days=7)
    obj, _ = await http.object("adm_145332")
    assert obj["id"] == "adm_145332" and route.call_count == 1 and http.memory_hits == 1
    assert http.peek("adm_145332") is not None and http.peek("nothing_here") is None


async def test_one_request_at_a_time_at_least_the_interval_apart(router, tmp_path):
    router.post(ENDPOINT).mock(return_value=recorded("getObject__NIKERG-W3401.xml"))
    now = [100.0]
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    http = make_http(tmp_path, min_interval=1.0, clock=lambda: now[0], sleep=sleep)
    await http.call("getObject", [("itemId", "a1")], ttl_days=30)
    await http.call("getObject", [("itemId", "b2")], ttl_days=30)
    await http.call("getObject", [("itemId", "c3")], ttl_days=30)
    assert slept == [1.0, 1.0]


async def test_identical_calls_in_flight_share_one_request(router, http):
    gate = asyncio.Event()

    async def slow(request):
        await gate.wait()
        return recorded("getObject__NIKERG-W3401.xml")

    route = router.post(ENDPOINT).mock(side_effect=slow)
    calls = [asyncio.create_task(http.call(*GET_NIKOLAUSBERG, ttl_days=30)) for _ in range(3)]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*calls)
    assert route.call_count == 1 and http.shared_waits == 2
    assert all(r[0]["id"] == NIKOLAUSBERG for r in results)


async def test_a_5xx_without_a_fault_is_retried_once(router, http):
    route = router.post(ENDPOINT).mock(
        side_effect=[httpx.Response(503, text="busy"), recorded("getObject__NIKERG-W3401.xml")]
    )
    obj, _ = await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert obj["id"] == NIKOLAUSBERG and route.call_count == 2


async def test_a_429_honours_retry_after_up_to_the_cap(router, tmp_path):
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    router.post(ENDPOINT).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "120"}),
            httpx.Response(429, headers={"retry-after": "120"}),
        ]
    )
    http = make_http(tmp_path, sleep=sleep)
    with pytest.raises(GovError) as caught:
        await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert caught.value.code == "rate_limited" and slept == [30.0]


async def test_a_fault_is_gov_s_answer_and_is_not_retried(router, http):
    route = router.post(ENDPOINT).mock(return_value=fault())
    with pytest.raises(GovError) as caught:
        await http.call("searchByNameAndType", [("placename", "x"), ("types", "x")], ttl_days=7)
    assert caught.value.code == "fault" and route.call_count == 1


async def test_no_such_object_is_not_found_and_not_cached(router, http):
    route = router.post(ENDPOINT).mock(return_value=recorded("getObject__XXXXXXJO00AA.xml"))
    for _ in range(2):
        with pytest.raises(GovError) as caught:
            await http.object("XXXXXXJO00AA")
        assert caught.value.code == "not_found" and caught.value.status == 404
    assert route.call_count == 2
    assert http.last_error["error"] == "not_found"


async def test_a_bot_check_is_reported_as_one(router, http):
    page = "<html><head><title>Making sure you're not a bot!</title></head>anubis</html>"
    router.post(ENDPOINT).mock(return_value=httpx.Response(200, text=page))
    with pytest.raises(GovError) as caught:
        await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert caught.value.code == "challenge"


async def test_a_redirect_is_reported_not_followed(router, http):
    route = router.post(ENDPOINT).mock(
        return_value=httpx.Response(302, headers={"location": "https://example.org/"})
    )
    with pytest.raises(GovError) as caught:
        await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert caught.value.code == "redirected" and route.call_count == 1


async def test_a_dropped_connection_is_retried_then_reported(router, http):
    route = router.post(ENDPOINT).mock(side_effect=httpx.ConnectError("reset"))
    with pytest.raises(GovError) as caught:
        await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert caught.value.code == "no_response" and route.call_count == 2


async def test_a_timeout_is_not_retried(router, http):
    route = router.post(ENDPOINT).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(GovError) as caught:
        await http.call(*GET_NIKOLAUSBERG, ttl_days=30)
    assert caught.value.code == "timeout" and route.call_count == 1
