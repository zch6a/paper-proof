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
    bad = t.replace(r"\textbf{3.0}", "3.0").replace(r"\textbf{1.0}", "1.0").replace("c & 2.0", r"c & \textbf{2.0}")
    (tab,) = find_tables(bad)
    (f,) = bold_not_best(tab)
    assert "neither the highest nor the lowest (they run from 1 to 3)" in f.message


def test_several_bold_numbers_in_a_column_are_left_alone():
    # Bold for the best single model and the best ensemble (BERT's SQuAD table does this), or for ties.
    t = r"""\begin{tabular}{lc}
\toprule Model & F1 \\ \midrule
A & 88.5 \\ B (single) & \textbf{90.9} \\ C (ensemble) & \textbf{92.2} \\ D & 91.8 \\
\bottomrule\end{tabular}"""
    assert bold_not_best(find_tables(t)[0]) == []


def test_a_caption_that_gives_bold_another_meaning():
    t = r"""\begin{table}\caption{Results not significantly worse than the best are in bold.}\begin{tabular}{lc}
Model & Acc \\ \hline A & 70.0 \\ B & \textbf{69.5} \\ C & 60.0 \\ \end{tabular}\end{table}"""
    assert bold_not_best(find_tables(t)[0]) == []
    assert len(bold_not_best(find_tables(t.replace("not significantly worse than the best are in bold", "Main results"))[0])) == 1


def test_tables_with_models_in_columns_are_read_by_row():
    t = r"""\begin{tabular}{lccc}
\toprule Metric & GPT & OPT & Ours \\ \midrule
Accuracy & 50 & \textbf{60} & 55 \\ F1 & 80 & 70 & \textbf{85} \\ BLEU & \textbf{65} & 90 & 95 \\ Recall & \textbf{70} & 40 & 30 \\
\bottomrule\end{tabular}"""
    (f,) = bold_not_best(find_tables(t)[0])
    assert f.message == "table at :1, row BLEU: 65 is bold but 95 in the same row is higher"


def test_conventions_seen_in_real_papers_are_not_errors():
    # A diagonal of bold cells (ALiBi: train length = evaluation length).
    diag = r"""\begin{tabular}{rccc}\toprule Train & 64 & 128 & 256 \\ \midrule
64 & \textbf{28.5} & 24.7 & 22.9 \\ 128 & - & \textbf{24.0} & 21.7 \\ 256 & - & - & \textbf{21.3} \\ \bottomrule\end{tabular}"""
    assert bold_not_best(find_tables(diag)[0]) == []
    # Bold marks the largest values even where lower is better (MT-Bench's position-bias tables).
    extremes = r"""\begin{tabular}{lcc}\toprule Judge & Error & Loss \\ \midrule
A & \textbf{9.0} & 1.2 \\ B & 2.0 & \textbf{3.8} \\ C & 5.0 & 0.0 \\ D & 3.0 & 2.5 \\ \bottomrule\end{tabular}"""
    assert bold_not_best(find_tables(extremes)[0]) == []
    # Each row its own group, each with a bold (Mistral's table): best of each category.
    groups = r"""\begin{tabular}{lc}\toprule Model & NQ \\ \midrule
A & 24.7 \\ B & \textbf{29.0} \\ \midrule C & 11.0 \\ \midrule D & \textbf{28.8} \\ \bottomrule\end{tabular}"""
    assert bold_not_best(find_tables(groups)[0]) == []
    # \cmidrule between two header rows does not end the header (DINO's table with a Δ column).
    cmid = r"""\begin{tabular}{lccc}\toprule & \multicolumn{3}{c}{k-NN} \\ \cmidrule{2-4} & RN50 & ViT & $\Delta$ \\ \midrule
a & 1.0 & 2.0 & 1.0 \\ b & 3.0 & 4.0 & 1.0 \\ c & 2.0 & 9.0 & \textbf{7.0} \\ \bottomrule\end{tabular}"""
    (t,) = find_tables(cmid)
    assert t.header_rows == 2 and bold_not_best(t) == []


def test_header_without_a_rule_under_it():
    # LDM's FID table: header, then many result rows, and the first rule only near the end.
    t = r"""\begin{tabular}{lcc}
Method & FID $\downarrow$ & Recall $\uparrow$ \\
A & 15.8 & 0.40 \\ B & 10.2 & 0.46 \\ C & 8.0 & 0.45 \\ D & 7.7 & 0.48 \\ Ours & \textbf{9.1} & \textbf{0.50} \\
\hline Real data & 0.0 & 1.00 \\ \end{tabular}"""
    (tab,) = find_tables(t)
    assert tab.header_rows == 1
    (f,) = bold_not_best(tab)
    assert "9.1 is bold but 7.7 (D) is lower" in f.message


def test_two_claims_in_one_sentence_keep_their_own_numbers():
    s = r"SMA improves BLEU from 27.3 to 28.9, a 9.5\% relative gain, and cuts training from 42 to 10 hours, a 4.2$\times$ speedup."
    (f,) = change_claims(s, "a.tex", lines(s))
    assert "from 27.3 to 28.9" in f.message and "not 9.5%" in f.message


def test_abstract_differences_need_the_same_precision_and_unit():
    paper = r"""\begin{abstract}We are 1.8 BLEU above the baseline and 4.2$\times$ faster.\end{abstract}
\begin{tabular}{lcc}\toprule M & BLEU & Hours \\ \midrule A & 27.3 & 42 \\ B & 27.9 & 12 \\ C & 28.4 & 10 \\ \bottomrule\end{tabular}"""
    msgs = [f.message for f in abstract_numbers({"m.tex": paper}, find_tables(paper, "m.tex"))]
    # 1.8 is no difference of BLEU numbers (12 - 10 = 2 in whole hours does not count, nor 1.79% relative); 4.2 = 42/10
    assert len(msgs) == 1 and "says 1.8," in msgs[0]


def test_a_sentence_that_points_to_a_table():
    from paper_proof.numbers import table_mentions

    good = "Our model reaches 28.9 BLEU, 1.6 above the baseline (Table~\\ref{tab:main}), and trains in 10 hours."
    stale = "Our model reaches 29.1 BLEU (Table~\\ref{tab:main}), trained for 3.5 days on 8 GPUs."
    paper = TABLE + "\n" + good + "\n\n" + stale
    (f,) = table_mentions({"m.tex": paper}, find_tables(paper, "m.tex"))
    assert "29.1 (the table has 28.9)" in f.message and "3.5" not in f.message  # 3.5 is unlike anything in it


def test_an_average_column_that_does_not_add_up():
    from paper_proof.numbers import average_columns

    t = r"""\begin{tabular}{lcccc}\toprule Model & MNLI & SST-2 & QNLI & Avg. \\ \midrule
A & 84.0 & 92.0 & 90.0 & 88.7 \\ B & 85.0 & 93.0 & 91.0 & 89.7 \\ C & 86.0 & 94.0 & 89.0 & 89.7 \\ D & 87.0 & 95.0 & 92.0 & 92.1 \\
\bottomrule\end{tabular}"""
    (f,) = average_columns(find_tables(t)[0])
    assert "row D: Avg. is 92.1, but the mean of the 3 numbers before it" in f.message and "91.33" in f.message
    # a table whose rows mostly disagree defines its average some other way (weighted): left alone
    weighted = t.replace("88.7", "80.0").replace("89.7", "81.0")
    assert average_columns(find_tables(weighted)[0]) == []
    # "Avg. # tokens" is not an average of the row
    assert average_columns(find_tables(t.replace("Avg.", "Avg. \\# tokens"))[0]) == []


def test_a_range_is_not_a_change():
    s = "the relative performance gain ranging from 33\\% to 90\\% and averaging 62\\%."
    assert change_claims(s, "a.tex", lines(s)) == []


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
        "intro.tex": "\\section{Intro}\\label{sec:intro}\n\\label{sec:other}\n\\label{sec:other}",
    }
    kinds = sorted((f.kind, f.message.split(" ")[0] if f.kind != "unreferenced" else f.message) for f in labels(texts))
    assert ("duplicate-label", "label") in kinds
    # a duplicate nobody refers to is only a note; one that is referred to is an error
    sev = {f.severity for f in labels(texts) if f.kind == "duplicate-label"}
    assert sev == {"note"}
    texts["main.tex"] += "\\ref{sec:other}"
    assert {f.severity for f in labels(texts) if f.kind == "duplicate-label"} == {"error"}
    # labels inside a macro body or a toggle branch are not duplicates; #1 is a parameter, not a label
    macro = {"m.tex": r"\newcommand{\figa}{\begin{figure}\label{fig:x}\end{figure}}\iftoggle{v}{\label{fig:x}}{}\newcommand{\r}[1]{\ref{#1}}"}
    assert labels(macro) == [f for f in labels(macro) if f.kind == "unreferenced"]
    assert ("undefined-ref", "reference") in kinds
    assert ("unreferenced", "figure fig:a is never referred to in the text") in kinds
    assert not any("tab:main" in k[1] for k in kinds)


def test_check_numbers_orders_by_severity():
    paper = "\\begin{abstract}We get 99.9.\\end{abstract}\nSee \\ref{nope}." + TABLE
    sev = [f.severity for f in check_numbers({"main.tex": paper})]
    assert sev == sorted(sev, key=["error", "warning", "note"].index) and sev[0] == "error"
