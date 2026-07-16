import job


def test_confirm_accepts_y(answer_input):
    answer_input("y")
    assert job.confirm("Are you sure?") is True


def test_confirm_accepts_yes_case_insensitive(answer_input):
    answer_input("YES")
    assert job.confirm("Are you sure?") is True


def test_confirm_rejects_blank(answer_input):
    answer_input("")
    assert job.confirm("Are you sure?") is False


def test_confirm_rejects_n(answer_input):
    answer_input("n")
    assert job.confirm("Are you sure?") is False


def test_confirm_rejects_garbage(answer_input):
    answer_input("maybe")
    assert job.confirm("Are you sure?") is False


def test_confirm_eof_is_false(eof_input):
    assert job.confirm("Are you sure?") is False


def test_confirm_meridiem_am(answer_input):
    answer_input("am")
    assert job.confirm_meridiem(9, 0) == "am"


def test_confirm_meridiem_a_shorthand(answer_input):
    answer_input("a")
    assert job.confirm_meridiem(9, 0) == "am"


def test_confirm_meridiem_pm(answer_input):
    answer_input("PM")
    assert job.confirm_meridiem(9, 0) == "pm"


def test_confirm_meridiem_p_shorthand(answer_input):
    answer_input("p")
    assert job.confirm_meridiem(9, 0) == "pm"


def test_confirm_meridiem_garbage_is_none(answer_input):
    answer_input("whenever")
    assert job.confirm_meridiem(9, 0) is None


def test_confirm_meridiem_eof_is_none(eof_input):
    assert job.confirm_meridiem(9, 0) is None
