import common.embeddings as E


def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "CACHE_PATH", tmp_path / "cache.jsonl")
    monkeypatch.setattr(E, "_cache", None)
    calls = []

    def fake_voyage(texts, input_type):
        calls.append((tuple(texts), input_type))
        return E.Embeddings([[0.1, 0.2] for _ in texts], 5)

    monkeypatch.setattr(E, "_voyage", fake_voyage)
    monkeypatch.setenv("EMBED_PROVIDER", "voyage")
    monkeypatch.delenv("EMBED_CACHE", raising=False)
    return calls


def test_second_identical_query_is_served_from_cache(monkeypatch, tmp_path):
    calls = fresh(monkeypatch, tmp_path)
    first = E.embed_query("Which outages are open?")
    second = E.embed_query("Which outages are open?")
    assert len(calls) == 1 and second.vectors == first.vectors and second.tokens == 0


def test_cache_survives_a_restart(monkeypatch, tmp_path):
    calls = fresh(monkeypatch, tmp_path)
    E.embed_query("persist me")
    monkeypatch.setattr(E, "_cache", None)  # simulate a new process reading the file
    E.embed_query("persist me")
    assert len(calls) == 1


def test_cache_can_be_disabled_and_is_per_text(monkeypatch, tmp_path):
    calls = fresh(monkeypatch, tmp_path)
    E.embed_query("a"); E.embed_query("b")
    assert len(calls) == 2
    monkeypatch.setenv("EMBED_CACHE", "0")
    E.embed_query("a"); E.embed_query("a")
    assert len(calls) == 4


def test_rate_limit_switches_on_pacing_for_every_thread(monkeypatch):
    monkeypatch.setattr(E, "_interval", 0.0)
    monkeypatch.setattr(E, "_interval_pinned", False)
    monkeypatch.setattr(E, "_next_allowed", 0.0)
    E._rate_limited(2.0)
    assert E._interval == 21.0 and E._next_allowed > 0
