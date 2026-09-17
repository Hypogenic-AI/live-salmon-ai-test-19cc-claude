"""report_template.md is the frozen structure: six combination rows, empty outcome
cells, and the required scope caveats.  REPORT.md is the working copy: it must keep
that structure, and it must stay empty for as long as no formal run has happened.
"""
import re

from infocond.paths import EXP_DIR, RUNS_DIR

TEMPLATE = EXP_DIR / "report_template.md"
REPORT = EXP_DIR / "REPORT.md"

REQUIRED_STATEMENTS = [
    "one model", "two fixed datasets", "five formal repetitions",
    "no estimate of general performance across datasets",
    "input length, information, and analysis cues change together",
    "position effects",
    "do not guarantee identification of the true mechanism",
    "unchanged model identifier does not guarantee an unchanged backend",
    "cannot by themselves establish model drift",
    "reported separately",
]


def _rows(text):
    rows = []
    for line in text.splitlines():
        if re.match(r"^\|\s*(live_salmon|dead_salmon)\s*\|", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    return rows


def _tables(text):
    return [t for t in text.split("\n\n") if "| live_salmon |" in t]


def test_template_has_six_rows_per_table_with_empty_outcome_cells():
    """The frozen template never carries results, whatever REPORT.md later says."""
    tables = _tables(TEMPLATE.read_text())
    assert len(tables) >= 2, "expected execution and claims tables"
    for table in tables:
        rows = _rows(table)
        assert len(rows) == 6
        assert {(r[0], r[1]) for r in rows} == {(d, c) for d in ("live_salmon", "dead_salmon") for c in ("A", "A_prime", "B")}
        for r in rows:
            fixed = 3 if r[2] == "5" else 2       # dataset, condition[, planned=5]
            assert all(c == "" for c in r[fixed:]), f"outcome cell not empty: {r}"


def _outcome_tables(text):
    """Split into (header_cells, row_keys) for every table carrying combination rows."""
    tables, header, rows = [], None, []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if re.match(r"^\|\s*(live_salmon|dead_salmon)\s*\|", line):
                rows.append((cells[0], cells[1]))
            elif not set("".join(cells)) <= set("-: "):
                if rows:
                    tables.append((header, rows)); rows = []
                header = tuple(cells)
        else:
            if rows:
                tables.append((header, rows)); rows = []
    if rows:
        tables.append((header, rows))
    return tables


SIX = {(d, c) for d in ("live_salmon", "dead_salmon") for c in ("A", "A_prime", "B")}


def test_report_keeps_the_frozen_structure():
    """REPORT.md is not in the design hash, so its conformance is tested instead.

    Checked per table rather than by counting rows: every table that carries combination
    rows must carry all six exactly once, and every header the template defines must
    still be present in the report with the same columns.  The filled report may add
    tables the template does not have; it may not drop, rename or reorder a column of
    one the template defines, and it may not lose a combination.
    """
    report, template = REPORT.read_text(), TEMPLATE.read_text()
    assert re.findall(r"^## .+$", report, re.M) == re.findall(r"^## .+$", template, re.M)

    rtables, ttables = _outcome_tables(report), _outcome_tables(template)
    assert ttables, "template defines no outcome table"
    for header, rows in rtables:
        assert len(rows) == 6 and set(rows) == SIX, f"table {header} does not carry the six combinations once each"
    rheaders = [h for h, _ in rtables]
    for theader, trows in ttables:
        assert set(trows) == SIX
        assert theader in rheaders, f"the report dropped or renamed the template table {theader}"


def test_template_states_required_caveats():
    text = TEMPLATE.read_text().lower()
    for s in REQUIRED_STATEMENTS:
        assert s.lower() in text, s


def test_report_contains_no_results_until_a_formal_run_exists():
    if (RUNS_DIR / "formal" / "summary.json").exists():
        return          # results may legitimately be written up from here on
    text = REPORT.read_text()
    section = text.split("## Results")[1].split("## Scope")[0] if "## Results" in text else ""
    assert section
    assert not re.search(r"\b\d+\s*/\s*5\b|\b\d+%|\bp\s*[<=]", section), "results section must not contain outcomes yet"
