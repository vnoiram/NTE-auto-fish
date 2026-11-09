from types import SimpleNamespace

from modules.game_window import auto_select_monitor, pick_monitor_index

MONS = [SimpleNamespace(x=0, y=0), SimpleNamespace(x=1920, y=0)]


def test_pick_matches_origin():
    assert pick_monitor_index(MONS, (1920, 0, 3840, 1080)) == 1
    assert pick_monitor_index(MONS, (5, 5, 10, 10)) is None
    assert pick_monitor_index(MONS, None) is None


def test_auto_select_respects_flag(monkeypatch):
    cfg = SimpleNamespace(monitor_index=0, monitor_auto_select=False)
    assert auto_select_monitor(cfg) is False
    assert cfg.monitor_index == 0


def test_auto_select_sets_index(monkeypatch):
    import modules.game_window as gw

    monkeypatch.setattr(gw, "find_game_monitor_rect", lambda: (1920, 0, 3840, 1080))
    import screeninfo

    monkeypatch.setattr(screeninfo, "get_monitors", lambda: MONS)
    cfg = SimpleNamespace(monitor_index=0, monitor_auto_select=True)
    assert auto_select_monitor(cfg) is True
    assert cfg.monitor_index == 1
