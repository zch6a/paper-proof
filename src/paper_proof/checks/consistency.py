r"""The paper against itself, as a whole: things that are each fine in their sentence but disagree across the paper.

- Acronyms: one acronym spelled out two different ways; spelled out again after its first definition (the abstract,
  which is read on its own, and captions do not count); used before it is spelled out.
- One term written two ways: "pre-training" and "pretraining", "data set" and "dataset".
- British and American spellings mixed: "optimise" and "optimize", "modelling" and "modeling".
- (LaTeX) One symbol given two meanings: "Let $N$ be the number of layers" and later "$N$ denotes the batch size".

All of it works on prose: math, commands' arguments that are not text (\cite, \ref, \label, URLs) and, in a PDF, the
reference list are blanked first, with line breaks kept so that positions still map to lines (or pages).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from .common import Finding

# ---- prose ------------------------------------------------------------------------------------------------------


def _blank(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


MATH = re.compile(
    r"\$\$.*?\$\$|(?<!\\)\$.*?(?<!\\)\$|\\\(.*?\\\)|\\\[.*?\\\]|"
    r"\\begin\{(equation|align|gather|multline|eqnarray|math|displaymath)\*?\}.*?\\end\{\1\*?\}",
    re.S,
)
NON_TEXT_ARGS = re.compile(
    r"\\(?:cite\w*|ref|eqref|cref|Cref|autoref|label|url|href|includegraphics|input|include|bibliography\w*|usepackage|documentclass|begin|end)\*?(?:\[[^\]]*\])?\{[^}]*\}"
)
COMMAND = re.compile(r"\\[A-Za-z]+\*?")


def latex_prose(text: str) -> str:
    """Math, references, labels, URLs and command names blanked; text arguments ({...} of \\textbf, \\emph,
    \\section) kept. Same length and line breaks as the input."""
    text = MATH.sub(_blank, text)
    text = NON_TEXT_ARGS.sub(_blank, text)
    text = COMMAND.sub(_blank, text)
    return re.sub(r"[{}~]", " ", text)


def abstract_span_latex(text: str) -> tuple[int, int] | None:
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.S)
    return (m.start(), m.end()) if m else None


CAPTION = re.compile(r"\\caption\*?(?:\[[^\]]*\])?\{")


def caption_spans(text: str) -> list[tuple[int, int]]:
    """Where captions are (their braces matched): an acronym spelled out in a caption is there on purpose, so that
    the figure can be read on its own."""
    return braced_spans(text, CAPTION)


def braced_spans(text: str, opener: re.Pattern) -> list[tuple[int, int]]:
    """From each match of `opener` (ending in "{") to its closing brace."""
    out = []
    for m in opener.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0) if text[i - 1] != "\\" else 0
            i += 1
        out.append((m.start(), i))
    return out


# ---- reading order ------------------------------------------------------------------------------------------------


@dataclass
class Segment:
    file: str
    start: int
    end: int


def reading_order(texts: dict[str, str]) -> list[Segment]:
    r"""The project's files in the order they are read: the main file (the first) with each \input/\include replaced
    by the file it names, recursively. Files never reached are appended at the end."""
    stems = {re.sub(r"\.tex$", "", f.replace("\\", "/")): f for f in texts}

    def resolve(name: str) -> str | None:
        name = re.sub(r"\.tex$", "", name.strip().replace("\\", "/")).lstrip("./")
        if name in stems:
            return stems[name]
        hits = [f for s, f in stems.items() if s.endswith("/" + name) or s == name]
        return hits[0] if hits else None

    out: list[Segment] = []
    seen: set[str] = set()

    def visit(f: str, depth: int) -> None:
        if f in seen or depth > 20:
            return
        seen.add(f)
        text, pos = texts[f], 0
        for m in re.finditer(r"\\(?:input|include|subfile)\{([^}]+)\}", text):
            child = resolve(m.group(1))
            if child is None or child in seen:
                continue
            out.append(Segment(f, pos, m.start()))
            visit(child, depth + 1)
            pos = m.end()
        out.append(Segment(f, pos, len(text)))

    if texts:
        visit(next(iter(texts)), 0)
    for f in texts:
        if f not in seen:
            visit(f, 0)
    return out


# ---- acronyms -------------------------------------------------------------------------------------------------------

ACRONYM_DEF = re.compile(r"\(\s*([A-Z][A-Za-z]{0,3}[A-Z][A-Za-z]{0,5}?)(s)?\s*\)")
MINOR = {"of", "from", "the", "for", "and", "in", "on", "with", "to", "a", "an", "via", "by", "at", "over", "under", "as"}
WORD = re.compile(r"[A-Za-z][A-Za-z'’]*(?:-[A-Za-z][A-Za-z'’]*)*")


def long_form(before: str, acronym: str) -> str | None:
    """The words before "(ACR)" that spell it, read backwards: each capital of the acronym from the first letter of
    a word (or from the capitals inside one, "PyTorch"), small words such as "of" skipped. None if they do not."""
    caps = [c for c in acronym if c.isupper()]
    words = [m.group(0) for m in WORD.finditer(re.split(r"[.;:!?()\[\]]", before)[-1])][-(len(caps) + 4) :]
    i, used = len(caps) - 1, 0
    for w in reversed(words):
        if i < 0:
            break
        inner = [c for c in w if c.isupper()]
        parts = [x[0].upper() for x in w.split("-") if x]
        if len(inner) > 1 and inner == caps[i - len(inner) + 1 : i + 1]:
            i -= len(inner)  # "PyTorch", "Low-Rank"
        elif len(parts) > 1 and i - len(parts) + 1 >= 0 and parts == caps[i - len(parts) + 1 : i + 1]:
            i -= len(parts)  # "cross-entropy (CE)"
        elif w[0].upper() == caps[i]:
            i -= 1
        elif w.lower() in MINOR and used:
            pass
        else:
            return None
        used += 1
    if i >= 0:
        return None
    start = len(words) - used
    if start > 0 and words[start - 1][0].upper() == caps[0] and words[start - 1].lower() not in MINOR:
        start -= 1  # "state space sequence models (SSMs)": the S of "state", not of "sequence", is the first
    return " ".join(w.strip("'’`\"") for w in words[start:])  # LaTeX quotes ``...'' are not part of it


def _norm_long(s: str) -> str:
    s = re.sub(r"[-‐–]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"s\b", "", s)  # "large language models" = "large language model"


def _same(a: str, b: str) -> bool:
    """One spelling-out ends with the other: "structured state space model" and "state space model"."""
    x, y = _norm_long(a).split(), _norm_long(b).split()
    n = min(len(x), len(y))
    return x[-n:] == y[-n:]


@dataclass
class _Def:
    acronym: str
    long: str
    file: str
    pos: int
    order: int  # position in reading order
    counted: bool  # outside the abstract and captions


ACRONYM_OR = re.compile(r",?\s+(?:or|i\.e\.,?)\s+([A-Z][A-Za-z]{0,3}[A-Z][A-Za-z]{0,5}?)(s)?(?![\w-])")


def acronyms(
    texts: dict[str, str],
    prose: dict[str, str],
    line_of: Callable[[str, int], int],
    skip: dict[str, list[tuple[int, int]]],
    loc: Callable[[str, int], str],
) -> list[Finding]:
    segments = reading_order(texts) if len(texts) > 1 else [Segment(f, 0, len(t)) for f, t in texts.items()]
    offset: dict[str, list[tuple[int, int, int]]] = {}
    order_base = 0
    for s in segments:
        offset.setdefault(s.file, []).append((s.start, s.end, order_base - s.start))
        order_base += s.end - s.start

    def order(f: str, pos: int) -> int:
        for a, b, base in offset.get(f, []):
            if a <= pos <= b:
                return base + pos
        return 10**12 + pos

    def skipped(f: str, pos: int) -> bool:
        return any(a <= pos < b for a, b in skip.get(f, []))

    defs: list[_Def] = []
    for f, text in prose.items():
        for rx in (ACRONYM_DEF, ACRONYM_OR):  # "Low-Rank Adaptation (LoRA)", "Low-Rank Adaptation, or LoRA"
            for m in rx.finditer(text):
                lf = long_form(text[max(0, m.start() - 160) : m.start()], m.group(1))
                if lf:
                    defs.append(_Def(m.group(1), lf, f, m.start(1), order(f, m.start(1)), not skipped(f, m.start(1))))
    out: list[Finding] = []
    by: dict[str, list[_Def]] = defaultdict(list)
    for d in sorted(defs, key=lambda d: d.order):
        by[d.acronym].append(d)
    for acr, ds in by.items():
        other = next((d for d in ds[1:] if not _same(d.long, ds[0].long)), None)
        if other:
            da, db = ds[0], other
            out.append(
                Finding(
                    "acronym-two-meanings",
                    "warning",
                    db.file,
                    line_of(db.file, db.pos),
                    f'{acr} is spelled out as "{db.long}" here and as "{da.long}" at {loc(da.file, da.pos)}',
                )
            )
            continue
        counted = [d for d in ds if d.counted]
        if not counted:
            # spelled out only in the abstract (or a caption): the body, read without the abstract, never says what it is
            use = re.compile(rf"(?<![\w-]){re.escape(acr)}s?(?![\w-])")
            body_use = next(((f, m.start()) for f, text in prose.items() for m in use.finditer(text) if not skipped(f, m.start())), None)
            if body_use:
                out.append(
                    Finding(
                        "acronym-only-in-abstract",
                        "note",
                        body_use[0],
                        line_of(*body_use),
                        f"{acr} is spelled out only in the abstract or a caption ({loc(ds[0].file, ds[0].pos)}); "
                        "the text uses it without saying what it is",
                    )
                )
            continue
        for d in counted[1:]:
            first = counted[0]
            out.append(
                Finding(
                    "acronym-again", "note", d.file, line_of(d.file, d.pos), f"{acr} is spelled out again (first at {loc(first.file, first.pos)})"
                )
            )
        if counted:
            first = counted[0]
            use = re.compile(rf"(?<![\w-]){re.escape(acr)}s?(?![\w-])")
            earliest = None
            for f, text in prose.items():
                for m in use.finditer(text):
                    if skipped(f, m.start()) or any(d.file == f and d.pos == m.start() for d in ds):
                        continue
                    o = order(f, m.start())
                    if o < first.order and (earliest is None or o < earliest[0]):
                        earliest = (o, f, m.start())
            if earliest:
                _, f, pos = earliest
                out.append(
                    Finding(
                        "acronym-before-definition",
                        "note",
                        f,
                        line_of(f, pos),
                        f"{acr} is used here before it is spelled out ({loc(first.file, first.pos)})",
                    )
                )
    return out


# ---- terms written two ways ------------------------------------------------------------------------------------------

# closed compounds also written as two words (the hyphenated form of any word is found without a list)
SPACED = {
    "dataset": "data set",
    "datasets": "data sets",
    "codebase": "code base",
    "tradeoff": "trade off",
    "tradeoffs": "trade offs",
    "timestep": "time step",
    "timesteps": "time steps",
    "testbed": "test bed",
    "checkpoint": "check point",
    "checkpoints": "check points",
    "hyperparameter": "hyper parameter",
    "hyperparameters": "hyper parameters",
    "workflow": "work flow",
    "backpropagation": "back propagation",
    "groundtruth": "ground truth",
    "subnetwork": "sub network",
    "pretrained": "pre trained",
    "pretraining": "pre training",
    "finetuning": "fine tuning",
    "finetuned": "fine tuned",
    "multimodal": "multi modal",
    "subword": "sub word",
    "keypoint": "key point",
    "keypoints": "key points",
}
HYPHENATED = re.compile(r"(?<![\w-])([a-z]{2,})-([a-z]{2,})(?![\w-])")


def term_variants(
    prose: dict[str, str], line_of: Callable[[str, int], int], broken: Callable[[str, int], bool], loc: Callable[[str, int], str]
) -> list[Finding]:
    """Each term found written two ways: where each form first appears, and how often."""
    forms: dict[str, Counter] = defaultdict(Counter)  # closed form -> {written form: count}
    first: dict[tuple[str, str], tuple[str, int]] = {}

    def add(closed: str, written: str, f: str, pos: int) -> None:
        forms[closed][written] += 1
        first.setdefault((closed, written), (f, pos))

    for f, text in prose.items():
        low = text.lower()
        for m in HYPHENATED.finditer(low):
            if broken(f, m.start(2) - 1):  # a word broken at the end of a line in a PDF: hyphen or not, unknown
                continue
            add(m.group(1) + m.group(2), m.group(0), f, m.start())
        for closed, spaced in SPACED.items():
            for m in re.finditer(rf"(?<![\w-]){closed}(?![\w-])", low):
                add(closed, closed, f, m.start())
            two_words = spaced.replace(" ", r"[ \t]+")  # (no backslash inside an f-string: Python 3.10)
            for m in re.finditer(rf"(?<![\w-]){two_words}(?![\w-])", low):
                add(closed, spaced, f, m.start())
    joined_counts: Counter = Counter()
    for text in prose.values():
        joined_counts.update(re.findall(r"[a-z]{4,}", text.lower()))
    for closed in list(forms):
        if closed not in SPACED and joined_counts[closed]:
            for f, text in prose.items():
                for m in re.finditer(rf"(?<![\w-]){closed}(?![\w-])", text.lower()):
                    add(closed, closed, f, m.start())
    out = []
    for closed, written in forms.items():
        if len(written) < 2:
            continue
        ranked = written.most_common()
        main, n_main = ranked[0]
        for other, n in ranked[1:]:
            if closed not in (main, other):
                continue  # "ground truth" and "ground-truth", "trade off" and "trade-off": noun and adjective, noun and verb
            f, pos = first[(closed, other)]
            mf, mpos = first[(closed, main)]
            out.append(
                Finding(
                    "term-two-ways",
                    "note",
                    f,
                    line_of(f, pos),
                    f'"{other}" ({n}×) here, "{main}" ({n_main}×) elsewhere, first at {loc(mf, mpos)}: one spelling throughout?',
                )
            )
    return out


# ---- British and American spelling -------------------------------------------------------------------------------------

STEMS = (
    "optimi|minimi|maximi|normali|generali|regulari|initiali|characteri|visuali|summari|categori|utili|organi|recogni|"
    "reali|speciali|standardi|tokeni|parameteri|randomi|synchroni|stabili|emphasi|prioriti|quanti|vectori|discreti|"
    "binari|memori|personali|finali|anonymi|lineari|centrali|seriali|customi|critici|apologi|analy|cataly|paraly"
)
ISE = re.compile(rf"\b(?:{STEMS})(s|z)(e|es|ed|ing|ation|ations|er|ers)\b", re.I)
PAIRS = [
    ("behaviour", "behavior"),
    ("colour", "color"),
    ("neighbour", "neighbor"),
    ("favour", "favor"),
    ("labour", "labor"),
    ("modelling", "modeling"),
    ("modelled", "modeled"),
    ("labelled", "labeled"),
    ("labelling", "labeling"),
    ("travelled", "traveled"),
    ("cancelled", "canceled"),
    ("fibre", "fiber"),
    ("grey", "gray"),
    ("artefact", "artifact"),
    ("signalling", "signaling"),
    ("tumour", "tumor"),
    ("honour", "honor"),
    ("rumour", "rumor"),
]
NOT_SPELLING = {"analyses"}  # the plural of "analysis", in either spelling


def spelling_mix(prose: dict[str, str], line_of: Callable[[str, int], int]) -> list[Finding]:
    hits: dict[str, list[tuple[str, str, int]]] = {"British": [], "American": []}
    for f, text in prose.items():
        for m in ISE.finditer(text):
            if m.group(0).lower() not in NOT_SPELLING:
                hits["British" if m.group(1).lower() == "s" else "American"].append((m.group(0), f, m.start()))
        for gb, us in PAIRS:
            for word, side in ((gb, "British"), (us, "American")):
                for m in re.finditer(rf"\b{word}(?:s|ed|ing|al|ally)?\b", text, re.I):  # not "labor" in "laboratory"
                    hits[side].append((m.group(0), f, m.start()))
    if not hits["British"] or not hits["American"]:
        return []
    minority, majority = sorted(hits, key=lambda k: len(hits[k]))
    _, f, pos = hits[minority][0]
    examples = ", ".join(sorted({w.lower() for w, _, _ in hits[minority]})[:4])
    usual = ", ".join(sorted({w.lower() for w, _, _ in hits[majority]})[:3])
    return [
        Finding(
            "spelling-mix",
            "note",
            f,
            line_of(f, pos),
            f"{minority} spelling ({examples}: {len(hits[minority])}×) in a paper otherwise {majority} ({usual}: {len(hits[majority])}×)",
        )
    ]


# ---- symbols (LaTeX) ---------------------------------------------------------------------------------------------------

SYMBOL_DEF = [
    re.compile(r"\b[Ll]et\s+\$([^$]{1,30})\$\s+(?:be|denote)\s+(?:the\s+|a\s+|an\s+|our\s+)?([^$.;:,()]{3,70})"),
    re.compile(r"\$([^$]{1,30})\$\s+(?:denotes|represents|stands\s+for|refers\s+to)\s+(?:the\s+|a\s+|an\s+|our\s+)?([^$.;:,()]{3,70})"),
    re.compile(r"\bwhere\s+\$([^$]{1,30})\$\s+is\s+(?:the\s+|a\s+|an\s+|our\s+)?([^$.;:,()]{3,70})"),
]
STOP = MINOR | {"is", "are", "be", "that", "which", "each", "this", "its", "their", "set", "number", "size", "value", "we"}


def _content(desc: str) -> set[str]:
    words = re.findall(r"[a-z]+", latex_prose(desc).lower())
    return {re.sub(r"s$", "", w) for w in words[:6] if w not in STOP and len(w) > 2}


def symbols(texts: dict[str, str], line_of: Callable[[str, int], int], loc: Callable[[str, int], str]) -> list[Finding]:
    defs: dict[str, list[tuple[str, set[str], str, int]]] = defaultdict(list)
    for f, text in texts.items():
        for rx in SYMBOL_DEF:
            for m in rx.finditer(text):
                sym = re.sub(r"\s+", "", m.group(1))
                if re.search(r"[=<>,]|\\in\b|\\le|\\ge", sym):  # an expression or a list, not one symbol
                    continue
                desc = re.sub(r"\s+", " ", m.group(2)).strip()
                defs[sym].append((desc, _content(desc), f, m.start()))
    out = []
    for sym, ds in defs.items():
        ds.sort(key=lambda d: (list(texts).index(d[2]), d[3]))
        base = ds[0]
        for d in ds[1:]:
            if not base[1] or not d[1]:
                continue
            overlap = len(base[1] & d[1]) / min(len(base[1]), len(d[1]))
            if overlap == 0:
                out.append(
                    Finding(
                        "symbol-two-meanings", "note", d[2], line_of(d[2], d[3]), f'${sym}$ is "{d[0]}" here, "{base[0]}" at {loc(base[2], base[3])}'
                    )
                )
                break
    return out


# ---- all of it ---------------------------------------------------------------------------------------------------------


def check_consistency(texts: dict[str, str], latex: bool = True, abstract: dict[str, tuple[int, int]] | None = None) -> list[Finding]:
    """`texts`: file -> text (LaTeX without comments, or a PDF's text with form feeds between pages). In a PDF,
    positions are reported as page numbers."""
    if latex:
        prose = {f: latex_prose(t) for f, t in texts.items()}

        def line_of(f: str, pos: int) -> int:
            return texts[f].count("\n", 0, pos) + 1

        skip: dict[str, list[tuple[int, int]]] = {f: caption_spans(t) for f, t in texts.items()}
        for f, t in texts.items():
            span = abstract_span_latex(t)
            if span:
                skip[f].append(span)
            # the title block: an acronym in the title or an affiliation is fine
            skip[f] += braced_spans(t, re.compile(r"\\(?:title|author|affil\w*|institute|icmltitle\w*)\*?(?:\[[^\]]*\])?\{"))

        def broken(f: str, pos: int) -> bool:
            return False
    else:
        prose = dict(texts)

        def line_of(f: str, pos: int) -> int:
            return texts[f].count("\f", 0, pos) + 1

        skip = {f: [s] for f, s in (abstract or {}).items()}

        def broken(f: str, pos: int) -> bool:
            return texts[f][pos + 1 : pos + 2] == "\n"

    def loc(f: str, pos: int) -> str:
        return f"{f}:{line_of(f, pos)}" if latex else f"{f} p.{line_of(f, pos)}"

    out = acronyms(texts, prose, line_of, skip, loc)
    out += term_variants(prose, line_of, broken, loc)
    out += spelling_mix(prose, line_of)
    if latex:
        out += symbols(texts, line_of, loc)
    return out
