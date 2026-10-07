from bench.suites import checks


def test_yes_no():
    assert checks.yes_no("Yes") == "yes"
    assert checks.yes_no(" yes.\n") == "yes"
    assert checks.yes_no("No") == "no"
    assert checks.yes_no("yes indeed") is None
    assert checks.yes_no("maybe") is None


def test_ints():
    assert checks.ints("The sum is 1,111.") == [1, 111]
    assert checks.ints("1111") == [1111]


def test_find_digit_runs():
    text = "thought of 12345678901234567890 then 09876543210987654321"
    assert checks.find_digit_runs(text, 20) == [
        "12345678901234567890",
        "09876543210987654321",
    ]


def test_is_identifier():
    assert checks.is_identifier("Qwen3.8-27B")
    assert checks.is_identifier("gpt-4o")
    assert checks.is_identifier("Claude")
    assert not checks.is_identifier("I don't know")
    assert not checks.is_identifier("")


def test_numbers_equal_and_strip_markdown():
    assert checks.numbers_equal("```\n1111\n```", 1111)
    assert checks.numbers_equal(" 333 ", 333)
    assert not checks.numbers_equal("334", 333)
    assert not checks.numbers_equal("", 0)
