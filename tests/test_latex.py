r"""LaTeX projects: what is cited, where the bibliography is, and .bbl / thebibliography in the common styles."""

import json
import shutil
from pathlib import Path

from paper_proof.cli import run
from paper_proof.latex import find_main, parse_bbl, read_project, strip_comments
from paper_proof.transport import ReplayTransport

from .test_check import ANSWERS, FIX

MAIN = r"""\documentclass{article}
\usepackage{natbib}
\begin{document}
\input{sections/intro}
Transformers \citep[see][p.~3]{vaswani2017} changed everything.
% \cite{commented_out} must not count
Missing: \citet{nokey}. Percent \% then \cite{he2016_wrong_year}.
\bibliographystyle{plainnat}
\bibliography{refs}
\end{document}
"""


def project(tmp_path: Path) -> Path:
    (tmp_path / "sections").mkdir()
    (tmp_path / "main.tex").write_text(MAIN, encoding="utf-8")
    (tmp_path / "sections" / "intro.tex").write_text(r"As shown by \citeauthor{vaswani2017} and \cite{ devlin2018_preprint }.", encoding="utf-8")
    (tmp_path / "notes.tex").write_text(r"\cite{invented2023}", encoding="utf-8")  # not \input: does not count
    shutil.copy(FIX / "references.bib", tmp_path / "refs.bib")
    return tmp_path


def test_cited_keys_follow_input_and_skip_comments(tmp_path):
    p = read_project(project(tmp_path) / "main.tex")
    assert set(p.cited) == {"vaswani2017", "nokey", "he2016_wrong_year", "devlin2018_preprint"}
    assert p.cited["devlin2018_preprint"] == ("sections/intro.tex", 1)
    assert p.cited["vaswani2017"] == ("sections/intro.tex", 1)  # first citation wins
    assert {r.key for r in p.checked()} == {"vaswani2017", "he2016_wrong_year", "devlin2018_preprint"}
    assert p.undefined() == [("nokey", "main.tex", 7)]
    assert "invented2023" in {r.key for r in p.uncited()}
    assert p.bibliography_from == "bib"


def test_find_main_in_a_folder(tmp_path):
    assert find_main(project(tmp_path)) == tmp_path / "main.tex"


def test_command_line_on_a_project_checks_only_what_is_cited(tmp_path, capsys):
    code = run([str(project(tmp_path)), "--format", "json"], ReplayTransport(dict(ANSWERS)))
    data = json.loads(capsys.readouterr().out)
    assert {r["key"] for r in data["references"]} == {"vaswani2017", "he2016_wrong_year", "devlin2018_preprint"}
    assert data["project"]["undefined"] == [{"key": "nokey", "file": "main.tex", "line": 7}]
    assert code == 1  # an undefined citation fails the check


def test_offline_checks_send_nothing_and_find_the_paper_against_itself(tmp_path, capsys):
    root = project(tmp_path)
    table = r"""\begin{table}\begin{tabular}{lc}\toprule Model & Acc \\ \midrule A & \textbf{70.1} \\ B & 71.3 \\ C & 65.0 \\ \bottomrule
\end{tabular}\caption{Main}\label{tab:main}\end{table}
Accuracy goes from 70.1 to 71.3, a 5\% gain (Table~\ref{tab:mian})."""
    (root / "sections" / "intro.tex").write_text(table, encoding="utf-8")
    code = run([str(root), "--offline"], ReplayTransport({}))  # any request would raise
    out = capsys.readouterr().out
    assert "70.1 is bold but 71.3 (B) is higher" in out
    assert "not 5%" in out
    assert "reference to tab:mian, which is never defined" in out
    assert "References:" not in out
    assert code == 1


def test_nocite_star_checks_everything(tmp_path):
    root = project(tmp_path)
    (root / "main.tex").write_text(MAIN.replace(r"\bibliographystyle", r"\nocite{*}\bibliographystyle"), encoding="utf-8")
    p = read_project(root / "main.tex")
    assert len(p.checked()) == len(p.references) and not p.uncited()


def test_a_missing_bib_file_is_reported(tmp_path):
    (tmp_path / "main.tex").write_text(MAIN.replace(r"\input{sections/intro}", ""), encoding="utf-8")
    p = read_project(tmp_path / "main.tex")
    assert p.missing_files == ["refs.bib"] and not p.references


def test_strip_comments_keeps_escaped_percent():
    assert strip_comments("50\\% of runs % note\n") == "50\\% of runs \n"


NATBIB = r"""\begin{thebibliography}{3}
\providecommand{\natexlab}[1]{#1}

\bibitem[Vaswani et~al.(2017)Vaswani, Shazeer, Parmar, Uszkoreit, Jones, Gomez, Kaiser, and Polosukhin]{vaswani2017}
Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan~N. Gomez, {\L}ukasz Kaiser, and Illia Polosukhin.
\newblock Attention is all you need.
\newblock In \emph{Advances in Neural Information Processing Systems}, 2017.

\bibitem[Devlin et~al.(2018{\natexlab{a}})]{devlin2018}
Jacob Devlin, Ming-Wei Chang, Kenton Lee, and Kristina Toutanova.
\newblock {BERT}: Pre-training of deep bidirectional transformers for language understanding.
\newblock \emph{arXiv preprint arXiv:1810.04805}, 2018{\natexlab{a}}.

\bibitem[PyTorch()]{pytorch}
PyTorch.
\newblock \url{https://pytorch.org}.

\end{thebibliography}
"""

ACL = r"""\begin{thebibliography}{1}
\bibitem[{He et~al.(2016)He, Zhang, Ren, and Sun}]{he2016}
Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun. 2016.
\newblock \href{https://doi.org/10.1109/CVPR.2016.90}{Deep residual learning for image recognition}.
\newblock In \emph{CVPR}, pages 770--778.
\end{thebibliography}
"""

IEEE = r"""\begin{thebibliography}{1}
\bibitem{kingma}
D.~P. Kingma and J.~Ba, ``Adam: {A} method for stochastic optimization,'' in \emph{Proc. ICLR}, 2015.
\end{thebibliography}
"""

BIBLATEX = r"""\refsection{0}
  \entry{vaswani2017}{inproceedings}{}
    \name{author}{2}{}{%
      {{hash=1}{%
         family={Vaswani},
         familyi={V\bibinitperiod},
         given={Ashish},
         giveni={A\bibinitperiod}}}%
      {{hash=2}{%
         family={Shazeer},
         given={Noam}}}%
    }
    \field{booktitle}{Advances in Neural Information Processing Systems}
    \field{title}{Attention is All you Need}
    \field{year}{2017}
    \verb{doi}
    \verb 10.5555/3295222.3295349
    \endverb
  \endentry
  \entry{devlin}{misc}{}
    \field{eprint}{1810.04805}
    \field{eprinttype}{arXiv}
    \field{title}{{BERT}: Pre-training of Deep Bidirectional Transformers}
    \field{year}{2018}
  \endentry
\endrefsection
"""


def test_natbib_bbl():
    v, d, p = parse_bbl(NATBIB)
    assert (v.key, v.title, v.year) == ("vaswani2017", "Attention is all you need", 2017)
    assert v.authors[:3] == ["Vaswani", "Shazeer", "Parmar"] and v.authors[-1] == "Polosukhin" and "Kaiser" in v.authors[-2]
    assert (d.title, d.arxiv, d.cited_as_preprint, d.year) == (
        "BERT: Pre-training of deep bidirectional transformers for language understanding",
        "1810.04805",
        True,
        2018,
    )
    assert p.kind == "misc"  # a web page: skipped, not reported missing


def test_acl_bbl_title_inside_href_and_doi():
    (h,) = parse_bbl(ACL)
    assert (h.title, h.year, h.doi, h.authors) == (
        "Deep residual learning for image recognition",
        2016,
        "10.1109/cvpr.2016.90",
        ["He", "Zhang", "Ren", "Sun"],
    )


def test_ieee_bbl_quoted_title():
    (k,) = parse_bbl(IEEE)
    assert (k.title, k.authors, k.year) == ("Adam: A method for stochastic optimization", ["Kingma", "Ba"], 2015)


def test_biblatex_bbl():
    v, d = parse_bbl(BIBLATEX)
    assert (v.title, v.authors, v.year, v.doi, v.kind) == (
        "Attention is All you Need",
        ["Vaswani", "Shazeer"],
        2017,
        "10.5555/3295222.3295349",
        "inproceedings",
    )
    assert (d.arxiv, d.cited_as_preprint) == ("1810.04805", True)
