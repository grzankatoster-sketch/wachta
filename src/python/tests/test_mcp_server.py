import io
import json
from pathlib import Path

import pytest

from wachta_detectors.mcp_server import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL,
    handle,
    serve,
)
from wachta_detectors.tools import Tool, Toolbox, build_toolbox

FIXTURES = Path(__file__).resolve().parents[3] / "eval" / "fixtures"


def box() -> Toolbox:
    b = Toolbox()
    b.add(Tool("echo", "Oddaje to, co dostal.",
               {"type": "object", "properties": {"co": {"type": "string"}}},
               lambda a: {"echo": a.get("co", "")}))
    b.add(Tool("wybuch", "Zawsze sie wywraca.", {"type": "object"},
               lambda a: (_ for _ in ()).throw(RuntimeError("padlo"))))
    return b


def call(method: str, params: dict | None = None, request_id: int | None = 1, toolbox=None):
    message = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        message["id"] = request_id
    if params is not None:
        message["params"] = params
    return handle(message, toolbox or box())


def payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


def test_initialize_answers_with_the_protocol_version():
    r = call("initialize")
    assert r["result"]["protocolVersion"] == PROTOCOL
    assert r["result"]["serverInfo"]["name"] == "wachta"
    assert "tools" in r["result"]["capabilities"]


def test_tools_list_describes_every_tool_with_a_schema():
    tools = call("tools/list")["result"]["tools"]
    assert {t["name"] for t in tools} == {"echo", "wybuch"}
    assert all(t["inputSchema"]["type"] == "object" for t in tools)
    assert all(t["description"] for t in tools)


def test_tools_call_returns_a_text_content_block():
    r = call("tools/call", {"name": "echo", "arguments": {"co": "czesc"}})
    assert r["result"]["content"][0]["type"] == "text"
    assert payload(r) == {"echo": "czesc"}


def test_a_tool_that_raises_is_a_tool_error_not_a_protocol_error():
    # Model musi umiec to przeczytac i sprobowac czegos innego, a nie dostac "zle wywolanie".
    r = call("tools/call", {"name": "wybuch"})
    assert "error" not in r
    assert r["result"]["isError"] is True
    assert "padlo" in payload(r)["blad"]


def test_unknown_tool_lists_the_ones_that_exist():
    r = call("tools/call", {"name": "nie_ma_takiego"})
    assert r["error"]["code"] == INVALID_PARAMS
    assert "echo" in r["error"]["message"]


def test_call_without_a_name_is_refused():
    assert call("tools/call", {})["error"]["code"] == INVALID_PARAMS


def test_unknown_method_is_refused():
    assert call("kompletnie/inna")["error"]["code"] == METHOD_NOT_FOUND


def test_ping_is_answered():
    assert call("ping")["result"] == {}


def test_a_notification_gets_no_answer_at_all():
    # Odpowiedz na powiadomienie lamie protokol; czesc klientow sie na tym zawiesza.
    assert call("notifications/initialized", request_id=None) is None


def test_message_without_jsonrpc_version_is_refused():
    assert handle({"method": "ping", "id": 1}, box())["error"]["code"] == INVALID_REQUEST


def test_arguments_may_be_omitted_entirely():
    assert payload(call("tools/call", {"name": "echo"})) == {"echo": ""}


def test_serve_reads_lines_and_writes_one_response_per_request():
    wejscie = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
    wyjscie = io.StringIO()
    serve(box(), wejscie, wyjscie)
    linie = [json.loads(l) for l in wyjscie.getvalue().splitlines() if l.strip()]
    assert [l["id"] for l in linie] == [1, 2]      # powiadomienie nie dostalo odpowiedzi


def test_serve_survives_a_broken_line_and_keeps_going():
    wejscie = io.StringIO("to nie jest json\n"
                          + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n")
    wyjscie = io.StringIO()
    serve(box(), wejscie, wyjscie)
    linie = [json.loads(l) for l in wyjscie.getvalue().splitlines() if l.strip()]
    assert linie[0]["error"]["code"] == PARSE_ERROR
    assert linie[1]["id"] == 7


def test_blank_lines_are_ignored():
    wejscie = io.StringIO("\n\n" + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}) + "\n")
    wyjscie = io.StringIO()
    serve(box(), wejscie, wyjscie)
    assert len(wyjscie.getvalue().strip().splitlines()) == 1


def test_a_tool_cannot_be_registered_twice():
    b = box()
    with pytest.raises(ValueError):
        b.add(Tool("echo", "duplikat", {"type": "object"}, lambda a: {}))


def test_real_toolbox_exposes_the_detectors():
    box_real = build_toolbox(FIXTURES)
    assert "ciche_statki" in box_real.names()
    assert "przeladunki" in box_real.names()
    assert "tozsamosc_statkow" in box_real.names()


def test_every_real_tool_answer_carries_its_own_caveat():
    # Model powtorzy zastrzezenie tylko wtedy, gdy je dostanie razem z danymi.
    box_real = build_toolbox(FIXTURES)
    for name in box_real.names():
        try:
            answer = box_real.call(name, {"ile": 1})
        except FileNotFoundError:
            continue        # snapshot moze nie istniec na swiezym klonie
        assert answer.get("zastrzezenie"), f"{name} oddaje dane bez zastrzezenia"


def test_limit_is_clamped_to_something_sane():
    box_real = build_toolbox(FIXTURES)
    try:
        answer = box_real.call("wsparcie_ukrainy", {"ile": 100000})
    except FileNotFoundError:
        pytest.skip("brak aid_snapshot.json")
    assert len(answer["darczyncy"]) <= 100


def test_nonsense_limit_falls_back_instead_of_crashing():
    box_real = build_toolbox(FIXTURES)
    try:
        answer = box_real.call("wsparcie_ukrainy", {"ile": "duzo"})
    except FileNotFoundError:
        pytest.skip("brak aid_snapshot.json")
    assert len(answer["darczyncy"]) == 10


def test_search_tool_appears_only_when_search_is_available():
    assert "szukaj_zdarzen" not in build_toolbox(FIXTURES).names()
    assert "szukaj_zdarzen" in build_toolbox(FIXTURES, search=lambda q, k: []).names()


def test_search_tool_requires_a_question():
    box_real = build_toolbox(FIXTURES, search=lambda q, k: [])
    with pytest.raises(ValueError):
        box_real.call("szukaj_zdarzen", {})


def test_empty_search_result_is_an_answer_not_an_error():
    box_real = build_toolbox(FIXTURES, search=lambda q, k: [])
    answer = box_real.call("szukaj_zdarzen", {"pytanie": "cokolwiek"})
    assert answer["znalezione"] == 0
    assert "nie jest blad" in answer["zastrzezenie"] or "odpowiedz" in answer["zastrzezenie"]
