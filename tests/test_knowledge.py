from torquespec import knowledge
from torquespec.diagnose import ChatTurn, build_messages, build_system


def kb():
    return knowledge.load()


def test_data_loads_and_has_core_specs():
    k = kb()
    names = {t.component for t in k.torque}
    assert {"Lug nuts", "Spark plugs", "Oil drain plug", "Cylinder head bolts"} <= names
    assert all(t.low <= t.high for t in k.torque)


def test_unit_conversion():
    lug = kb().search_torque("lug")[0]
    lo, hi = lug.nm
    assert lo == round(65 * knowledge.FT_LB_TO_NM, 1)
    assert hi == round(87 * knowledge.FT_LB_TO_NM, 1)
    cam = kb().search_torque("camshaft cap")[0]
    assert cam.unit == "in-lb" and cam.nm[0] < 15


def test_search_requires_all_words():
    assert [t.component for t in kb().search_torque("head bolts")] == ["Cylinder head bolts"]
    assert kb().search_torque("flux capacitor") == []
    assert len(kb().search_torque("")) == len(kb().torque)


def test_lookup_code_pads_digits():
    assert kb().lookup_code("8")["circuit"].startswith("Airflow meter")
    assert kb().lookup_code("99") is None


def test_match_issues_finds_relevant_problem():
    hits = kb().match_issues("idle surges and it stalls at every stop")
    assert hits and hits[0]["title"] == "Rough or hunting idle"
    assert kb().match_issues("zzz") == []


def test_reference_is_deterministic_and_complete():
    a, b = kb().render_reference(), kb().render_reference()
    assert a == b
    assert "Cylinder head bolts" in a and "[verify]" in a and "34:" in a


def test_prompt_is_cacheable_and_hints_are_appended():
    system = build_system(kb())
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    msgs = build_messages(kb(), [ChatTurn("user", "rough idle that surges when warm")])
    assert "Rough or hunting idle" in msgs[-1]["content"]
