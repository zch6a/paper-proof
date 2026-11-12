"""References from a PDF: a small PDF is written by hand (no real paper), read back with pypdf, split and parsed."""

import json
from pathlib import Path

from paper_proof.cli import run
from paper_proof.pdf import reference_from_string, references_from_pdf, references_section, split_entries
from paper_proof.transport import ReplayTransport


def make_pdf(path: Path, lines: list[str]) -> Path:
    """A one-page PDF with one line of Helvetica text per item (ASCII only)."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["BT", "/F1 9 Tf", "11 TL", "40 800 Td"] + [f"({esc(x)}) Tj T*" for x in lines] + ["ET"]
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


AUTHOR_YEAR = [
    "6 Conclusion",
    "We are done.",
    "References",
    "Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Lukasz",
    "Kaiser, and Illia Polosukhin. Attention is all you need. In Advances in Neural Information",
    "Processing Systems, 2017.",
    "Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun. Deep Residual Learning for Image",
    "Recognition. In CVPR, 2016.",
    "Wei Li and Hao Chen. Recursive gradient folding for self-supervised hyperbolic transformers.",
    "arXiv preprint arXiv:2304.99999, 2023.",
    "A Proofs",
    "Here is a proof with a citation-like line. Not a reference.",
]


def test_author_year_entries_from_a_pdf(tmp_path):
    refs = references_from_pdf(make_pdf(tmp_path / "p.pdf", AUTHOR_YEAR))
    assert [r.title for r in refs] == [
        "Attention is all you need",
        "Deep Residual Learning for Image Recognition",
        "Recursive gradient folding for self-supervised hyperbolic transformers",
    ]
    assert refs[0].authors[0] == "Vaswani" and refs[0].year == 2017
    assert refs[2].arxiv == "2304.99999" and refs[2].cited_as_preprint


def test_quirks_of_pdf_text_seen_in_real_papers():
    # a space before the period of an initial (DPO's PDF), "et al." ending the authors, no space after a period
    r = reference_from_string("1", "Y . Bai, A. Jones, K. Ndousse, et al. Training a helpful and harmless assistant. arXiv preprint, 2022.")
    assert r.title == "Training a helpful and harmless assistant" and r.authors[0] == "Bai"
    r = reference_from_string("2", "N. Kalchbrenner, L. Espeholt. Neural machine translation in linear time.arXiv preprint arXiv:1610.10099, 2017.")
    assert r.title == "Neural machine translation in linear time" and r.arxiv == "1610.10099"
    r = reference_from_string(
        "3", "L. Kaiser and S. Bengio. Can active memory replace attention? In Advances in Neural Information Processing Systems, 2016."
    )
    assert r.title == "Can active memory replace attention?"
    r = reference_from_string("4", "D. Kingma and J. Ba. Adam: A method for stochastic optimization. In ICLR, 2015.")
    assert r.title == "Adam: A method for stochastic optimization"


def test_numbered_styles():
    bracketed = (
        "References\n[1] A. Vaswani, N. Shazeer. Attention is all you need. In NIPS, 2017.\n"
        "[2] K. He. Deep residual\nlearning. In CVPR, 2016.\n[3] J. Devlin. BERT. 2019.\n"
    )
    assert len(split_entries(references_section(bracketed))) == 3
    numbered = (
        "REFERENCES\n1. Vaswani, A.: Attention is all you need. NIPS (2017)\n"
        "2. He, K.: Deep residual learning. CVPR (2016)\n3. Devlin, J.: BERT. NAACL (2019)\n"
    )
    entries = split_entries(references_section(numbered))
    assert len(entries) == 3 and reference_from_string("1", entries[0]).title == "Attention is all you need"


def test_a_pdf_on_the_command_line_checks_only_references(tmp_path, capsys):
    pdf = make_pdf(tmp_path / "p.pdf", AUTHOR_YEAR)
    # with every database "down", all three are unknown, and no number check is attempted
    code = run([str(pdf), "--format", "json", "--fail-on", "never"], ReplayTransport(_down()))
    data = json.loads(capsys.readouterr().out)
    assert [r["status"] for r in data["references"]] == ["unknown"] * 3
    assert data["findings"] == [] and code == 0


class _down(dict):
    """Any URL: no answer."""

    def __contains__(self, url):
        return True

    def __getitem__(self, url):
        return (-1, "")
