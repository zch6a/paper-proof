r"""The paper against itself: tables, claimed changes, abstract numbers, labels (synthetic LaTeX, no network)."""

from paper_proof.numbers import abstract_numbers, bold_not_best, change_claims, check_numbers, labels
from paper_proof.tables import find_tables, parse_value

TABLE = r"""
\begin{table}[t]
\caption{Results on WMT14.}
\label{tab:main}
\begin{tabular}{lcc}
\toprule
Model & BLEU $\uparrow$ & PPL $\downarrow$ \\
\midrule
Baseline & 27.3 & 4.92 \\
Big & \textbf{28.1} & 4.33 \\
\midrule
Ours & 28.4 & \textbf{4.35} \\
Ours-large & \multicolumn{1}{c}{28.9} & 4.80 \\
\bottomrule
\end{tabular}
\end{table}
"""


def test_tables_are_read_with_rules_groups_and_bold():
    (t,) = find_tables(TABLE, "main.tex")
    assert t.label == "tab:main" and t.caption == "Results on WMT14."
    assert t.header_rows == 1 and t.header(1) == "BLEU \\uparrow"
    assert [c.value for _, c in t.column(1)] == [27.3, 28.1, 28.4, 28.9]
    assert t.groups[1:] == [0, 0, 1, 1]
    assert t.rows[2][1].bold and t.rows[2][1].line == 10


def test_bold_that_is_not_best():
    (t,) = find_tables(TABLE, "main.tex")
    f = bold_not_best(t)
    # BLEU: 28.1 is bold, but 28.9 (and 28.4) are higher, also within its own group? No: 28.1 is best of its group.
    # PPL: 4.35 is bold, 4.33 in another group is lower, but 4.35 is the best of its own group -> fine.
    assert f == []
    t.groups = [0] * len(t.rows)  # one group: now both are wrong
    msgs = [x.message for x in bold_not_best(t)]
    assert any("28.1 is bold but 28.9 (Ours-large) is higher" in m for m in msgs)
    assert any("4.35 is bold but 4.33 (Big) is lower" in m for m in msgs)


def test_direction_unknown_accepts_either_extreme():
    t = r"""\begin{tabular}{lc}
Method & Value \\ \hline
a & 1.0 \\
b & \textbf{3.0} \\
c & 2.0 \\
d & \textbf{1.0} \\
\end{tabular}"""
    (tab,) = find_tables(t)
    assert bold_not_best(tab) == []
    bad = t.replace(r"\textbf{3.0}", "3.0").replace("c & 2.0", r"c & \textbf{2.0}")
    (tab,) = find_tables(bad)
    assert len(bold_not_best(tab)) == 1


def test_parse_value():
    assert parse_value(r"$\mathbf{75.30}_{\pm 0.2}$")[:2] == (75.3, 2)
    assert parse_value("1,024")[:2] == (1024.0, 0)
    assert parse_value(r"72.4$^\dagger$")[:2] == (72.4, 1)


def lines(text):
    return lambda pos: text.count("\n", 0, pos) + 1


def test_change_claims():
    ok = "Accuracy improves from 80.0 to 84.0, a 5\\% relative gain. It rises from 50.0\\% to 55.0\\%, 5 points."
    assert change_claims(ok, "a.tex", lines(ok)) == []
    also_ok = "Error drops from 10.0 to 8.0 (20\\%)."
    assert change_claims(also_ok, "a.tex", lines(also_ok)) == []
    bad = "Our method improves BLEU from 27.3 to 28.4, a 14\\% improvement."
    (f,) = change_claims(bad, "a.tex", lines(bad))
    assert "4.0% relative change (1.1 points), not 14%" in f.message
    speed = "Latency goes from 120 to 40 ms, a 3.5x speedup."
    (f,) = change_claims(speed, "a.tex", lines(speed))
    assert "3.00×, not 3.5×" in f.message
    rounding = "from 33.3 to 50.0, a 50\\% increase."  # 50.0/33.3 = 1.5015...: within rounding
    assert change_claims(rounding, "a.tex", lines(rounding)) == []


def test_abstract_numbers():
    paper = (
        r"""\begin{abstract}
We reach 28.4 BLEU, 1.1 BLEU above the baseline (+4.0\%), and 31.7 on GPT-3.5 prompts.
\end{abstract}
"""
        + TABLE
    )
    msgs = [f.message for f in abstract_numbers({"main.tex": paper}, find_tables(paper, "main.tex"))]
    # 28.4 is in the table; 1.1 = 28.4 - 27.3; 4.0% = relative change; 31.7 appears nowhere; 3.5 is a version
    assert len(msgs) == 1 and "31.7" in msgs[0]


def test_labels():
    texts = {
        "main.tex": "\\begin{figure}\\caption{x}\\label{fig:a}\\end{figure}\nSee Table~\\ref{tab:main} and \\cref{sec:intro,fig:b}.\n" + TABLE,
        "intro.tex": "\\section{Intro}\\label{sec:intro}\n\\label{sec:intro}",
    }
    kinds = sorted((f.kind, f.message.split(" ")[0] if f.kind != "unreferenced" else f.message) for f in labels(texts))
    assert ("duplicate-label", "label") in kinds
    assert ("undefined-ref", "reference") in kinds
    assert ("unreferenced", "figure fig:a is never referred to in the text") in kinds
    assert not any("tab:main" in k[1] for k in kinds)


def test_check_numbers_orders_by_severity():
    paper = "\\begin{abstract}We get 99.9.\\end{abstract}\nSee \\ref{nope}." + TABLE
    sev = [f.severity for f in check_numbers({"main.tex": paper})]
    assert sev == sorted(sev, key=["error", "warning", "note"].index) and sev[0] == "error"
