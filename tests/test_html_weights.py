from copy import deepcopy

from hbqrs.html_weights import render_weight_configurator


def test_weight_configurator_covers_all_layers_and_is_offline(modules, bundle_by_id):
    html = render_weight_configurator(modules, bundle_by_id["prose.scene"])
    for text in ("Domains", "Components", "Groups", "Questions", "Penalty caps"):
        assert text in html
    assert "--weight-profile" in html
    assert "--local-weight-profile" in html
    assert "chapter/scene/unit weights" in html
    assert "fetch(" not in html
    assert "<script src=" not in html
    assert "innerHTML" not in html
    assert "localStorage" not in html


def test_weight_configurator_escapes_and_does_not_mutate(modules, bundle_by_id):
    selected = [deepcopy(modules[0])]
    selected[0]["title"] = "</script><img src=x>"
    bundle = {
        "bundle_id": "test.bundle",
        "domains": [{"domain_id": "d", "points": 100, "components": [{"module_id": selected[0]["module_id"]}]}],
        "module_ids": [selected[0]["module_id"]],
        "penalty_modules": [],
    }
    before = deepcopy(selected)
    html = render_weight_configurator(selected, bundle, title="<unsafe>")
    assert selected == before
    assert "<unsafe>" not in html
    assert "</script><img" not in html
