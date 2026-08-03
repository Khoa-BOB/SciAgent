from src.ingestion.validate import CheckResult, Check, parse_checks, print_report, VALIDATION_CYPHER_PATH


def test_parse_checks_reads_real_validation_file():
    checks = parse_checks(VALIDATION_CYPHER_PATH)

    assert len(checks) >= 5
    names = [check.name for check in checks]
    assert "papers_without_authors" in names
    assert len(names) == len(set(names)), "check names must be unique"

    for check in checks:
        assert check.description, f"{check.name} is missing a description"
        assert "RETURN" in check.query.upper()
        assert "violations" in check.query


def test_print_report_reports_failure(capsys):
    results = [
        CheckResult(check=Check(name="ok_check", description="fine", query=""), violations=0),
        CheckResult(check=Check(name="broken_check", description="bad data", query=""), violations=3),
    ]

    all_passed = print_report(results)

    assert all_passed is False
    output = capsys.readouterr().out
    assert "ok_check" in output and "PASS" in output
    assert "broken_check" in output and "FAIL" in output
    assert "bad data" in output


def test_print_report_all_pass():
    results = [
        CheckResult(check=Check(name="a", description="", query=""), violations=0),
        CheckResult(check=Check(name="b", description="", query=""), violations=0),
    ]

    assert print_report(results) is True
