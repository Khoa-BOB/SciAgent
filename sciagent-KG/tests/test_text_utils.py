from src.text_utils import normalize_name


def test_normalize_name_strips_accents_and_case():
    assert normalize_name("Igor Grabec") == "igor grabec"
    assert normalize_name("É. Grabec") == "e grabec"


def test_normalize_name_strips_punctuation():
    assert normalize_name("T. Kosel") == "t kosel"
    assert normalize_name("Jean-Paul Sartre") == "jean-paul sartre"


def test_normalize_name_collapses_whitespace():
    assert normalize_name("  Igor   Grabec  ") == "igor grabec"


def test_normalize_name_is_stable_across_calls():
    assert normalize_name("Igor Grabec") == normalize_name("Igor Grabec")
