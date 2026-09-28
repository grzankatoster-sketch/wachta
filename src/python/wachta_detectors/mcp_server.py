"""A Model Context Protocol server over stdio, so a model can call the detectors itself.

Written against the protocol rather than against an SDK, on purpose. MCP over stdio is JSON-RPC 2.0
with four messages that matter - `initialize`, the `notifications/initialized` acknowledgement,
`tools/list` and `tools/call` - and implementing them directly means the whole surface is testable
here, with no dependency to install in CI and no library version to track. If this server later needs
resources, prompts or sampling, an SDK earns its place; for a dozen tools it does not.

Two decisions worth naming:

  * a tool that raises returns an MCP tool error (`isError`), not a JSON-RPC error. A JSON-RPC error
    means "the call was malformed"; a failing detector means "the call worked and the answer is that
    something went wrong", and the model needs to be able to read that and try something else.
  * notifications get no reply at all. Answering one is a protocol violation that some clients
    tolerate and others hang on.
"""
import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

from .tools import Toolbox

PROTOCOL = "2024-11-05"
SERVER = {"name": "wachta", "version": "0.1.0"}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _result(request_id: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _as_content(payload: dict) -> dict:
    """MCP carries tool output as content blocks; JSON goes in a text block, pretty-printed.

    Readable indentation is not cosmetic here - the model reads this, and a single line of nested
    JSON costs it more attention than the answer is worth.
    """
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=1)}]}


def handle(message: dict, toolbox: Toolbox) -> dict | None:
    """One request in, one response out - or None for a notification, which must stay unanswered."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "oczekiwano JSON-RPC 2.0")

    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if request_id is None:
        return None                     # powiadomienie: odpowiedz na nie lamie protokol

    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER,
        })

    if method == "tools/list":
        return _result(request_id, {"tools": toolbox.describe()})

    if method == "tools/call":
        name = params.get("name")
        if not name:
            return _error(request_id, INVALID_PARAMS, "brak pola 'name'")
        try:
            return _result(request_id, _as_content(toolbox.call(name, params.get("arguments"))))
        except KeyError:
            return _error(request_id, INVALID_PARAMS,
                          f"nieznane narzedzie: {name}. Dostepne: {', '.join(toolbox.names())}")
        except Exception as e:
            # Detektor, ktory sie wywrocil, to poprawna odpowiedz o niepowodzeniu - nie blad wywolania.
            return _result(request_id, {**_as_content({"blad": f"{type(e).__name__}: {e}"}),
                                        "isError": True})

    if method == "ping":
        return _result(request_id, {})

    return _error(request_id, METHOD_NOT_FOUND, f"nieobslugiwana metoda: {method}")


def serve(toolbox: Toolbox, stdin: TextIO | None = None, stdout: TextIO | None = None,
          log: Callable[[str], None] | None = None) -> None:
    """Reads one JSON message per line and answers on stdout. Logs go to stderr, never stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            response = _error(None, PARSE_ERROR, f"niepoprawny JSON: {e}")
        else:
            try:
                response = handle(message, toolbox)
            except Exception as e:                      # obrona ostatniej szansy: serwer ma nie padac
                response = _error(message.get("id"), INTERNAL_ERROR, f"{type(e).__name__}: {e}")
        if response is None:
            continue
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()
        if log:
            log(f"{message.get('method', '?') if isinstance(message, dict) else '?'} -> ok")


def _build_search(fixtures, limit: int = 500):
    """Semantic search over the collected events, or None when it cannot be had.

    Indexing takes about two minutes and needs a local Ollama. Neither is guaranteed, and neither is
    required by the other seven tools, so a failure here costs the search tool and nothing else.
    """
    from .analyst import MIN_RELEVANT
    from .embeddings import OllamaEmbedder
    from .vector_store import Document, InMemoryVectorStore, index_documents

    snapshot = fixtures / "events_snapshot.json"
    if not snapshot.exists():
        raise FileNotFoundError("brak events_snapshot.json")

    def opis(e):
        parts = [e.get("actor1") or "", e.get("actor2") or "",
                 e.get("kind") or "", e.get("place") or ""]
        return " | ".join(p for p in parts if p)

    events = json.loads(snapshot.read_text(encoding="utf-8"))["events"]
    docs = [Document(str(e["id"]), opis(e), {"url": e.get("url")}) for e in events if opis(e)][:limit]

    embedder = OllamaEmbedder()
    store = InMemoryVectorStore()
    index_documents(store, embedder, docs)
    print(f"zaindeksowano {len(store)} zdarzen", file=sys.stderr)

    def search(pytanie: str, k: int = 8):
        return store.search(embedder.embed([pytanie])[0], k=k, min_score=MIN_RELEVANT)

    return search


def _build_db(dsn: str, connect_timeout: int = 10):
    """A factory of fresh connections to the live database, proven once before it is handed out.

    The probe matters: a factory that only fails on first use would let the database tools be
    advertised to the model and then break inside an answer. Better to find out at startup and offer
    fewer tools than to offer tools that do not work.
    """
    import psycopg

    with psycopg.connect(dsn, connect_timeout=connect_timeout) as probe:
        probe.execute("SELECT 1").fetchone()

    def connect():
        # Polaczenie na kazde wywolanie, jak w run.py: restart bazy ma kosztowac jedna odpowiedz,
        # a nie uniewaznic serwer do konca jego zycia.
        return psycopg.connect(dsn, connect_timeout=connect_timeout, autocommit=True)

    return connect


def build_from_env(fixtures, env=None) -> Toolbox:
    """The toolbox this process will serve, given what the environment actually provides.

    Every optional dependency is optional the same way: it costs its own tools and nothing else.
    No Ollama means no semantic search; no database (missing WACHTA_DB, wrong password, container
    down, psycopg not installed) means no live tools. The snapshot tools always work, so the server
    always starts - a model that gets seven tools can still do its job, a model that gets a stack
    trace cannot.
    """
    import os

    from .tools import build_toolbox

    env = os.environ if env is None else env
    search = None
    db = None

    if env.get("WACHTA_MCP_NO_SEARCH"):
        print("wyszukiwanie semantyczne wylaczone (WACHTA_MCP_NO_SEARCH)", file=sys.stderr)
    else:
        try:
            search = _build_search(fixtures)
        except Exception as e:
            print(f"wyszukiwanie semantyczne niedostepne ({type(e).__name__}: {e})", file=sys.stderr)

    dsn = env.get("WACHTA_DB")
    if not dsn:
        print("zywa baza niedostepna (brak WACHTA_DB) - zostaja migawki", file=sys.stderr)
    else:
        try:
            db = _build_db(dsn)
            print("zywa baza podlaczona", file=sys.stderr)
        except Exception as e:
            print(f"zywa baza niedostepna ({type(e).__name__}: {e}) - zostaja migawki", file=sys.stderr)

    return build_toolbox(fixtures, search, db)


def main() -> int:
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[3] / "eval" / "fixtures"
    toolbox = build_from_env(fixtures)
    print(f"WACHTA MCP gotowa, narzedzia: {', '.join(toolbox.names())}", file=sys.stderr)
    serve(toolbox)
    return 0


if __name__ == "__main__":
    sys.exit(main())
