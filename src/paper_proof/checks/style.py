r"""Style slips in a LaTeX paper that general grammar checkers miss or cannot see through LaTeX (offline):

- the same word twice ("the the"), also across a line break;
- "a" before a vowel sound or "an" before a consonant one, acronyms read letter by letter ("an LSTM", "a CNN");
- `Figure \ref{...}` with a plain space: LaTeX may break the line between "Figure" and its number (use `~`);
- references named two ways ("Fig." and "Figure", "Eq." and "Equation") before `\ref`;
- "et al" without its period, "et. al.", "e.g" or "i.e" missing a period;
- straight double quotes in the text ("word"): LaTeX prints both as closing quotes (write ``word'');
- `\cite{a}\cite{b}`: one `\cite{a,b}` prints one bracket.

Math, citations, labels, URLs and verbatim are left out. Every finding is a note: the author decides.
"""

from __future__ import annotations

import re
from collections import Counter

from .common import Finding
from .consistency import latex_prose

VERBATIM = re.compile(r"\\begin\{(verbatim|lstlisting|minted|alltt|comment)\*?\}.*?\\end\{\1\*?\}|\\(?:verb|lstinline)(.).*?\2", re.S)
URLS = re.compile(
    r"\\(?:url|href|path|nolinkurl)\{[^}]*\}"
    r"|\\[A-Za-z]*cite[A-Za-z]*\*?(?:\[[^\]]*\])*\{[^}]*\}"  # \newcite{parikh-etal:2016} too
    r"|\\begin\{(?:tabular\w*|array|longtable)\}(?:\{[^}]*\})?\{[^}]*\}"  # column specs: {cc cc}
    r"|\\(?:textcolor|color|colorbox|definecolor|hypersetup|cellcolor|rowcolor)\{[^}]*\}"
    r"|https?://\S+|www\.\S+"
)
REPEAT_OK = {
    "that",
    "had",
    "is",
    "can",
    "do",
    "so",
    "very",
    "bye",
    "no",
    "yes",
    "far",
    "more",
    "many",
    "ha",
    "et",
    "human",
    "assistant",
    "user",
    "system",
    "bot",
    "agent",
    "model",
}  # role labels in transcripts: "Human: ... human"
# "an" before these, though they start with a consonant letter; "a" before these vowel letters
AN_WORDS = re.compile(r"^(?:hour|honest|honou?r|heir|herb)", re.I)
A_WORDS = re.compile(
    r"^(?:uni(?:f|que|t|vers|on|corn|modal|variate|lateral|code|sex|cycle|son|ty|ax|form|direct)|use|usu|usa|uti|ure|eu|one\b|once|ewe|uk\b|us\b|u-|ubiq|uran|uro)",
    re.I,
)
VOWEL_LETTER_SOUND = set("AEFHILMNORSX")  # letters whose name starts with a vowel sound: "an F1", "an MLP"
REF_NAMES = [
    ("figure", re.compile(r"\b(Fig\.|Figs\.|Figure|Figures|fig\.|figure)(?:~|\s+)\\(?:ref|subref)\{")),
    ("equation", re.compile(r"\b(Eq\.|Eqs\.|Equation|Equations|eq\.|equation)(?:~|\s+)\\(?:ref|eqref)\{")),
    ("section", re.compile(r"\b(Sec\.|Secs\.|Section|Sections|Sect\.|§)(?:~|\s+)\\ref\{")),
]
NAME_SPACE_REF = re.compile(
    r"\b((?:Fig|Figs|Tab|Eq|Eqs|Sec|Secs|Sect|App|Alg|Thm|Def|Lem)\.?|Figure|Figures|Table|Tables|Equation|Section|Sections|Appendix|Algorithm|Theorem|Lemma|Definition|Line|Lines)(\s+)\\(ref|eqref|subref)\{"
)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _clean(text: str) -> str:
    """Verbatim, code and URLs blanked (same length), so nothing in them is read."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    return URLS.sub(blank, VERBATIM.sub(blank, text))


def _macro_line(text: str, pos: int) -> bool:
    """Whether the position is on a line that defines a macro (its text is not prose)."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return bool(
        re.search(
            r"\\(?:re)?newcommand|\\providecommand|\\def\b|\\DeclareMathOperator|\\newenvironment", text[start : end if end >= 0 else len(text)]
        )
    )


def article(word: str) -> str | None:
    """The article a word takes: "a", "an", or None when it cannot be told.

    >>> [article(w) for w in ["LSTM", "CNN", "MLP", "F1", "hour", "unified", "uninformed", "one-shot", "apple", "user", "SVM", "8-bit", "11"]]
    ['an', 'a', 'an', 'an', 'an', 'a', 'an', 'a', 'an', 'a', 'an', 'an', 'an']
    >>> article("U-Net"), article("mAP"), article("model"), article("UNet"), article("n-gram"), article("STEM")
    ('a', 'an', 'a', 'a', 'an', None)
    """
    w = word.strip("({[\"'`")
    if not w:
        return None
    if re.fullmatch(r"\d[\d.,]*(?:[-‐][A-Za-z]+)?%?", w):  # a number, as it is read: "an 8-bit", "an 11", "a 10"
        lead = w.split("-")[0].rstrip("%")
        if lead.startswith("8") or re.fullmatch(r"1[18](?:,\d{3})*", lead):
            return "an"
        return "a"
    core = re.split(r"[-‐/]", w)[0]
    if re.fullmatch(r"[a-z]", core) and w[1:2] not in ("-", "‐"):
        return None  # a lone lower-case letter is a variable ("a r"), not a word
    if (re.fullmatch(r"[A-Za-z]", core) and w[len(core) : len(core) + 1] in ("-", "‐", "")) or re.fullmatch(
        r"[a-z][A-Z][A-Za-z]*|[A-Z]{2}[a-z][A-Za-z]*", core
    ):
        # a letter read as a letter: "a U-Net", "an n-gram", "an mAP", "a UNet"
        return "an" if core[0].upper() in VOWEL_LETTER_SOUND else "a"
    if len(core) >= 2 and (core.isupper() or re.fullmatch(r"[A-Z][A-Z0-9]+[a-z]?s?", core)) and not re.fullmatch(r"[A-Z][a-z]+", core):
        if re.fullmatch(
            r"(?:NASA|NATO|OWL|UNESCO|LASSO|SIFT|SMOTE|ReLU|RAM|ROM|STEM|LLaMA|Llama|LLaMa|LAION|COCO|GLUE|SQuAD|RACE|BLEU|ROUGE|ADAM|LoRA|LORA|SOTA|MOS|ODE|OOD|URL|URI|UI)",
            core,
        ):
            return None  # read as a word: the first sound decides, and the tool will not guess
        return "an" if core[0].upper() in VOWEL_LETTER_SOUND else "a"
    if not core[0].isalpha():
        return None
    if AN_WORDS.match(core):
        return "an"
    if A_WORDS.match(core):
        return "a"
    return "an" if core[0].lower() in "aeiou" else "a"


SYMBOL_NEXT = {"is", "are", "was", "were", "be", "and", "or", "of", "to", "in", "on", "with", "then", "has", "have", "can", "will", "for",
               "at", "by", "as", "if", "that", "which", "=", "denotes", "contains"}  # fmt: skip
BULK = {"ref-space", "straight-quotes", "cite-merge"}  # one note per file, with how many


def check_style(texts: dict[str, str]) -> list[Finding]:
    found = _check(texts)
    out: list[Finding] = []
    groups: dict[tuple[str, str], list[Finding]] = {}
    for f in found:
        if f.kind in BULK:
            groups.setdefault((f.kind, f.file), []).append(f)
        else:
            out.append(f)
    for (_kind, _file), fs in groups.items():
        f = fs[0]
        more = f" (and {len(fs) - 1} more in this file)" if len(fs) > 1 else ""
        out.append(Finding(f.kind, f.severity, f.file, f.line, f.message + more))
    return out


def _check(texts: dict[str, str]) -> list[Finding]:
    out: list[Finding] = []
    names: dict[str, Counter[str]] = {}
    first: dict[tuple[str, str], tuple[str, int]] = {}
    for file, raw in texts.items():
        text = _clean(raw)
        prose = latex_prose(text)
        begin = text.find("\\begin{document}")
        body_start = begin if begin >= 0 else (0 if "\\documentclass" not in text else len(text))  # the preamble is not prose
        seen_repeats: set[tuple[int, str]] = set()
        for m in re.finditer(r"(?<![\w-])([a-z]+)(\s+)\1(?![\w-])", prose):
            w, ln = m.group(1), _line(prose, m.start(2))
            if w in REPEAT_OK or (len(w) == 1 and w != "a") or (ln, w) in seen_repeats or m.start() < body_start:
                continue
            if _macro_line(text, m.start()):
                continue
            seen_repeats.add((ln, w))
            out.append(Finding("repeated-word", "note", file, ln, f'"{w} {w}": a word written twice'))
        for m in re.finditer(r"(?<![\w-])(a|an|A|An)\s+([A-Za-z0-9][\w‐-]*)", prose):
            art, nxt = m.group(1).lower(), m.group(2)
            if m.start() < body_start:
                continue
            before = prose[max(0, m.start() - 3) : m.start()]
            if m.group(1) in ("A", "An") and (len(nxt) == 1 or nxt.lower() in SYMBOL_NEXT or not re.search(r"(?:^|[.!?:]\s+|\n\s*)$", before)):
                continue  # mid-sentence "A" is the letter A, a symbol, not the article
            if nxt.lower() in ("a", "an") or _macro_line(text, m.start()):
                continue
            if m.group(1) == "a" and nxt.lower() in SYMBOL_NEXT | {"against", "une", "la", "un", "priori", "posteriori", "fortiori"}:
                continue
            want = article(nxt)
            if want and want != art:
                out.append(Finding("article", "note", file, _line(prose, m.start()), f'"{m.group(1)} {nxt}": "{want}" before "{nxt}"'))
        for m in NAME_SPACE_REF.finditer(text):
            out.append(Finding("ref-space", "note", file, _line(text, m.start()),
                               f'"{m.group(1)} \\{m.group(3)}{{": a plain space; write "{m.group(1)}~\\{m.group(3)}{{" '
                               "so the line never breaks before the number"))  # fmt: skip
        for kind, rx in REF_NAMES:
            for m in rx.finditer(text):
                if _macro_line(text, m.start()) or m.start() < body_start:
                    continue  # \newcommand{\figref}[1]{Figure~\ref{#1}} defines, it does not use
                form = m.group(1).rstrip("s.").lower().rstrip("s")
                form = {
                    "fig": "Fig.",
                    "figure": "Figure",
                    "eq": "Eq.",
                    "equation": "Equation",
                    "sec": "Sec.",
                    "sect": "Sec.",
                    "section": "Section",
                    "§": "§",
                }.get(form, m.group(1))
                names.setdefault(kind, Counter())[form] += 1
                first.setdefault((kind, form), (file, _line(text, m.start())))
        for m in re.finditer(r"\bet\.?\s+al(?![.\w])|\bet\.\s+al\.|\b(e\.g|i\.e)(?![.\w])|\b(eg|ie)\.(?=\s*,)", prose):
            if m.start() < body_start or _macro_line(text, m.start()):
                continue
            out.append(Finding("abbreviation", "note", file, _line(prose, m.start()),
                               f'"{m.group(0)}": write "et al.", "e.g." and "i.e." with their periods'))  # fmt: skip
        for m in re.finditer(r'(?<![\\\w`])"(?=[A-Za-z])[^"\n]{1,80}"', prose):
            out.append(Finding("straight-quotes", "note", file, _line(prose, m.start()),
                               f"{m.group(0)[:40]}: straight double quotes print as two closing quotes in LaTeX; write ``...''"))  # fmt: skip
        raw_v = VERBATIM.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), raw)  # the citations themselves are needed here
        for m in re.finditer(r"\\cite[pt]?\*?(?:\[[^\]]*\])?\{[^}]*\}\s*[,;]?\s*~?\\cite[pt]?\*?(?:\[[^\]]*\])?\{", raw_v):
            if re.search(r"\\cite[pt]", m.group(0)):
                continue  # natbib's \citet/\citep in a row can be meant
            out.append(Finding("cite-merge", "note", file, _line(raw_v, m.start()), "two \\cite{...} in a row: \\cite{a,b} prints one bracket"))
    for kind, counter in names.items():
        if len(counter) > 1:
            (common, n), *others = counter.most_common()
            for form, k in others:
                f, ln = first[(kind, form)]
                out.append(
                    Finding("ref-name", "note", f, ln, f'"{form}" ({k}×) and "{common}" ({n}×) for the same kind of reference: one form throughout?')
                )
    return out
