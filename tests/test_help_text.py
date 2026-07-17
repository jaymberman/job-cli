import job


def test_print_usage_mentions_core_commands(capsys):
    job.print_usage()
    out = capsys.readouterr().out
    assert "Usage:" in out
    assert "job <company>" in out
    assert "job list" in out
    assert "job search" in out
    assert "job interviews" in out
    assert "job today" in out
    assert "job favorites" in out
    assert "--favorite" in out
    assert "--remove-favorite" in out
    assert "--rename" in out
    assert "--company" in out


def test_print_list_help(capsys):
    job.print_list_help()
    out = capsys.readouterr().out
    assert "Usage: job list" in out
    assert "sort" in out


def test_print_search_help(capsys):
    job.print_search_help()
    out = capsys.readouterr().out
    assert "Usage: job search" in out


def test_print_interviews_help(capsys):
    job.print_interviews_help()
    out = capsys.readouterr().out
    assert "Usage: job interviews" in out


def test_print_today_help(capsys):
    job.print_today_help()
    out = capsys.readouterr().out
    assert "Usage: job today" in out


def test_print_favorites_help(capsys):
    job.print_favorites_help()
    out = capsys.readouterr().out
    assert "Usage: job favorites" in out
