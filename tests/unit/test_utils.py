from ciceroscm import _utils


def test_check_numeric_pamset():
    required = {"Year": 2022, "number": 4.55, "test": 6.3e-4, "test2": 85}
    pamset = {
        "test": 7.8e-3,
        "test2": "string",
        "untouched": 44,
        "untouched_string": "Hello",
    }
    pamset2 = _utils.check_numeric_pamset(required, pamset)
    assert pamset2["Year"] == 2022
    assert pamset2["number"] == 4.55
    assert pamset2["test"] == 7.8e-3
    assert pamset2["test2"] == 85
    assert pamset2["untouched"] == 44
    assert pamset2["untouched_string"] == "Hello"
