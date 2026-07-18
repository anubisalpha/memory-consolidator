from guidance import AUTO_FIXABLE, GUIDANCE, guidance_for


def test_guidance_for_known_auto_fixable_category():
    assert "auto_fix_slug_mismatch" in guidance_for("slug_hygiene")


def test_guidance_for_known_manual_category():
    assert "kebab" not in guidance_for("invalid_type").lower()
    assert guidance_for("invalid_type") == GUIDANCE["invalid_type"]


def test_guidance_for_unknown_category_has_fallback():
    text = guidance_for("some_future_category_not_yet_documented")
    assert "no guidance recorded" in text.lower()


def test_auto_fixable_and_guidance_dicts_do_not_overlap():
    assert set(AUTO_FIXABLE) & set(GUIDANCE) == set()
