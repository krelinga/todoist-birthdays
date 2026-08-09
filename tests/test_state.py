import json

from birthday_todoist.state import StateStore


def test_missing_file_starts_empty(tmp_path):
    store = StateStore(tmp_path / "state.json")
    assert store.already_sent("jane doe", 2026) is False


def test_mark_sent_persists_to_disk(tmp_path):
    path = tmp_path / "data" / "state.json"
    store = StateStore(path)
    store.mark_sent("jane doe", 2026)

    assert json.loads(path.read_text()) == {"jane doe": 2026}


def test_already_sent_reflects_marked_year(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.mark_sent("jane doe", 2026)

    assert store.already_sent("jane doe", 2026) is True
    assert store.already_sent("jane doe", 2027) is False
    assert store.already_sent("john smith", 2026) is False


def test_state_survives_reload_from_disk(tmp_path):
    path = tmp_path / "state.json"
    StateStore(path).mark_sent("jane doe", 2026)

    reloaded = StateStore(path)
    assert reloaded.already_sent("jane doe", 2026) is True


def test_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "state.json"
    StateStore(path).mark_sent("jane doe", 2026)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]
