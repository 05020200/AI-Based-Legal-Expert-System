from backend.inference_engine.working_memory import WorkingMemory


def test_add_user_fact():
    wm = WorkingMemory()
    result = wm.add_fact("product_purchased", "true")
    assert result is True
    assert wm.get_fact("product_purchased") == {"value": "true", "source": "user"}


def test_add_derived_fact():
    wm = WorkingMemory()
    result = wm.add_derived_fact("defective_product_issue", "true")
    assert result is True
    assert wm.get_fact("defective_product_issue") == {"value": "true", "source": "derived"}


def test_has_fact():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    assert wm.has_fact("product_purchased") is True


def test_has_fact_with_expected_value():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    assert wm.has_fact("product_purchased", "true") is True


def test_has_fact_incorrect_value():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    assert wm.has_fact("product_purchased", "false") is False


def test_duplicate_fact():
    wm = WorkingMemory()
    first = wm.add_fact("product_purchased", "true")
    second = wm.add_fact("product_purchased", "true")
    assert first is True
    assert second is False
    all_facts = wm.get_all_facts()
    assert len(all_facts) == 1
    assert all_facts["product_purchased"] == {"value": "true", "source": "user"}


def test_get_all_facts():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("product_defective", "true")
    wm.add_derived_fact("defective_product_issue", "true")
    all_facts = wm.get_all_facts()
    expected = {
        "product_purchased": {"value": "true", "source": "user"},
        "product_defective": {"value": "true", "source": "user"},
        "defective_product_issue": {"value": "true", "source": "derived"},
    }
    assert all_facts == expected


def test_clear_memory():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("product_defective", "true")
    wm.clear()
    assert wm.get_all_facts() == {}
