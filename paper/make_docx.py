"""Make the Word (.docx) version of the IEEE paper from the generated LaTeX.

Run after build_paper.py, from the repo root:
    python3 paper/make_docx.py
The LaTeX file is the single source: this script resolves its references and citations,
converts it with pandoc, then lays the result out in IEEE conference style
(US Letter, title and authors across the page, body in two columns, Times New Roman).
"""
import copy
import os
import re
import subprocess
import sys
import tempfile

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_paper import OUT_NAME, PAPER  # noqa: E402
SUBTITLE = "BAMAT207 Probability and Statistics: Case Study Report"

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
FONT = "Times New Roman"
COL_W = Inches(3.5)
PAGE_W = Inches(7.25)


def roman(n):
    return ROMAN[n - 1]


# ---------------------------------------------------------------- LaTeX side
def prepare_tex(tex):
    title = re.search(r"\\title\{(.*?)\}\n", tex, re.S).group(1).strip()
    body = tex[tex.index("\\begin{document}") + len("\\begin{document}"):tex.index("\\end{document}")]
    body = re.sub(r"\\author\{.*?\n\}\n", "", body, flags=re.S)
    body = re.sub(r"\\author\{\\IEEEauthorblockN\{[^}]*\}\}\n", "", body)
    body = body.replace("\\FloatBarrier", "")
    body = body.replace("table*}", "table}").replace("figure*}", "figure}")
    body = body.replace("\\sup_t", "\\text{sup}_t").replace("Network & ", "Net. & ")
    body = body.replace("\\maketitle", "").replace("\\IEEEtriggeratref{12}", "")

    # numbering of labels in source order (LaTeX numbers floats in source order)
    labels = {}
    tcount = fcount = ecount = 0
    for m in re.finditer(r"\\begin\{(table\*?|figure\*?|equation|align)\}(.*?)\\end\{\1\}", body, re.S):
        env, inner = m.group(1), m.group(2)
        if env.startswith("table"):
            tcount += 1
            for lab in re.findall(r"\\label\{([^}]*)\}", inner):
                labels[lab] = roman(tcount)
        elif env.startswith("figure"):
            fcount += 1
            for lab in re.findall(r"\\label\{([^}]*)\}", inner):
                labels[lab] = str(fcount)
        else:
            lines = 1 if env == "equation" else inner.count("\\\\") + 1
            first = ecount + 1
            ecount += lines
            for lab in re.findall(r"\\label\{([^}]*)\}", inner):
                labels[lab] = str(first)
    body = re.sub(r"\\ref\{([^}]*)\}", lambda m: labels[m.group(1)], body)

    # citations -> [n]
    bm = re.search(r"\\begin\{thebibliography\}\{99\}(.*?)\\end\{thebibliography\}", body, re.S)
    bib = bm.group(1) if bm else ""
    keys = re.findall(r"\\bibitem\{([^}]*)\}", bib)
    order = {k: i + 1 for i, k in enumerate(keys)}

    def cite(m):
        nums = [order[k.strip()] for k in m.group(1).split(",")]
        return "[" + "], [".join(str(n) for n in nums) + "]"

    body = re.sub(r"~?\\cite\{([^}]*)\}", lambda m: " " + cite(m), body)
    refs = re.split(r"\\bibitem\{[^}]*\}", bib)[1:]
    ref_par = "\n\n".join(f"[{i + 1}] " + r.strip() for i, r in enumerate(refs))
    if bm:
        body = re.sub(r"\\begin\{thebibliography\}\{99\}.*?\\end\{thebibliography\}",
                      lambda m: "\\section*{References}\n\n" + ref_par, body, flags=re.S)

    body = body.replace("\\begin{IEEEkeywords}", "\\paragraph{KEYWORDS}").replace("\\end{IEEEkeywords}", "")
    body = re.sub(r"\\setlength\{\\tabcolsep\}\{[^}]*\}", "", body)
    body = body.replace("\\\\[2pt]\n\\raggedright\\scriptsize ", "\n\nTABLENOTE ")
    body = re.sub(r"\\label\{[^}]*\}", "", body)
    sup = str.maketrans("-0123456789", "\u207b\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")

    def lt_text(m):
        t = m.group(1)
        t = re.sub(r"\^\{([^}]*)\}", lambda mm: mm.group(1).translate(sup), t)
        t = t.replace("<", " < ").replace(">", " > ").replace("{", "").replace("}", "")
        return re.sub(r"\s+", " ", t).strip().replace("p < ", "\\textit{p} < ")

    body = re.sub(r"\$([^$]*)\$", lambda m: lt_text(m) if re.search(r"[<>]", m.group(1)) else m.group(0), body)
    # equations: mark each display with its number so it can be placed after conversion
    n = [0]

    def eq(m):
        env, inner = m.group(1), m.group(2)
        lines = [l for l in re.split(r"\\\\", inner)] if env == "align" else [inner]
        out = []
        for l in lines:
            n[0] += 1
            l = l.replace("&", "")
            out.append(f"\n\nEQNUM{n[0]}\n\\[{l.strip()}\\]\n\n")
        return "".join(out)

    body = re.sub(r"\\begin\{(equation|align)\}(.*?)\\end\{\1\}", eq, body, flags=re.S)
    body = body.replace("\\url{", "\\href{https://github.com/AashmanBiyani08/Prob_Stats_Project}{")
    return title, "\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n" + body + "\n\\end{document}\n"


# ---------------------------------------------------------------- Word helpers
def set_font(run, size=None, bold=None, italic=None, caps=None, small_caps=None):
    run.font.name = FONT
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), FONT)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if caps is not None:
        run.font.all_caps = caps
    if small_caps is not None:
        run.font.small_caps = small_caps
    run.font.color.rgb = RGBColor(0, 0, 0)


def fmt(p, size=10, align=None, before=0, after=0, indent=None, line=1.0):
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.line_spacing = line
    if align is not None:
        p.alignment = align
    if indent is not None:
        pf.first_line_indent = indent
    for r in p.runs:
        set_font(r, size=size)


def prefix_run(p, text, **font):
    run = p.add_run(text)
    set_font(run, **font)
    pPr = p._p.find(qn("w:pPr"))
    if pPr is not None:
        pPr.addnext(run._element)
    else:
        p._p.insert(0, run._element)
    return run


def strip_prefix(p, prefix):
    for t in p._p.iter(qn("w:t")):
        if t.text and prefix in t.text:
            t.text = t.text.replace(prefix, "", 1).lstrip()
            return


def clear_runs(p):
    for r in list(p.runs):
        r._element.getparent().remove(r._element)


def insert_paragraph_before(p, text="", style=None):
    new = p.insert_paragraph_before(text, style=style)
    return new


def section_break_after(paragraph, columns):
    """Make `paragraph` the last paragraph of a section with the given column count."""
    pPr = paragraph._p.get_or_add_pPr()
    sect = OxmlElement("w:sectPr")
    typ = OxmlElement("w:type")
    typ.set(qn("w:val"), "continuous")
    sect.append(typ)
    pg = OxmlElement("w:pgSz")
    pg.set(qn("w:w"), "12240")
    pg.set(qn("w:h"), "15840")
    sect.append(pg)
    mar = OxmlElement("w:pgMar")
    for k, v in dict(top="1080", bottom="1440", left="893", right="893", header="720", footer="720", gutter="0").items():
        mar.set(qn("w:" + k), v)
    sect.append(mar)
    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), str(columns))
    cols.set(qn("w:space"), "360")
    sect.append(cols)
    pPr.append(sect)


def table_borders(tbl):
    tblPr = tbl._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single"), e.set(qn("w:sz"), "8"), e.set(qn("w:color"), "000000")
        b.append(e)
    for edge in ("left", "right", "insideV", "insideH"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "nil")
        b.append(e)
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    tblPr.append(b)
    # rule under the header row
    for cell in tbl.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        tb = OxmlElement("w:tcBorders")
        bot = OxmlElement("w:bottom")
        bot.set(qn("w:val"), "single"), bot.set(qn("w:sz"), "4"), bot.set(qn("w:color"), "000000")
        tb.append(bot)
        tcPr.append(tb)


def set_table_widths(tbl):
    """Fit a table to one column, giving each column a share of the width by its longest text."""
    from docx.shared import Emu
    ncol = len(tbl.columns)
    def need(c):
        head = max((len(w) for w in tbl.rows[0].cells[c].text.split()), default=1)
        rest = max((len(r.cells[c].text) for r in tbl.rows[1:]), default=1)
        return max(head, rest) + 1
    longest = [need(c) for c in range(ncol)]
    total_dxa = int(COL_W / 635)  # EMU -> twips
    widths = [int(total_dxa * l / sum(longest)) for l in longest]
    tblPr = tbl._tbl.tblPr
    tw = tblPr.find(qn("w:tblW"))
    if tw is None:
        tw = OxmlElement("w:tblW")
        tblPr.append(tw)
    tw.set(qn("w:w"), str(sum(widths)))
    tw.set(qn("w:type"), "dxa")
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    grid = tbl._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(w))
    for row in tbl.rows:
        for cell, w in zip(row.cells, widths):
            tcPr = cell._tc.get_or_add_tcPr()
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW")
                tcPr.insert(0, tcW)
            tcW.set(qn("w:w"), str(w))
            tcW.set(qn("w:type"), "dxa")
            mar = OxmlElement("w:tcMar")
            for side in ("left", "right"):
                e = OxmlElement(f"w:{side}")
                e.set(qn("w:w"), "30"), e.set(qn("w:type"), "dxa")
                mar.append(e)
            tcPr.append(mar)


def main():
    tex_path = os.path.join(PAPER, OUT_NAME + ".tex")
    if not os.path.exists(tex_path):
        sys.exit("Run paper/build_paper.py first")
    title, ptex = prepare_tex(open(tex_path).read())
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.tex")
        raw = os.path.join(tmp, "raw.docx")
        open(src, "w").write(ptex)
        r = subprocess.run(["pandoc", src, "-f", "latex", "-t", "docx", "--resource-path",
                            os.path.join(PAPER, "figures"), "-o", raw], capture_output=True, text=True)
        warn = [l for l in r.stderr.splitlines() if "Could not" in l]
        if r.returncode or warn:
            sys.exit("pandoc problem:\n" + r.stderr)
        doc = Document(raw)

    # ---- page and base style
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.62)
    sec.top_margin, sec.bottom_margin = Inches(0.75), Inches(1)
    for sname in ("Normal", "Body Text", "First Paragraph", "Compact", "Abstract", "Bibliography"):
        try:
            st = doc.styles[sname]
            st.font.name, st.font.size = FONT, Pt(10)
        except KeyError:
            pass

    body = doc.paragraphs
    # ---- title and authors at the very top
    first = body[0]
    tp = insert_paragraph_before(first)
    tp.add_run(title)
    title_par = tp
    sub = doc.add_paragraph()
    tp._p.addnext(sub._p)
    set_font(sub.add_run(SUBTITLE), size=11)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    atbl = sub
    spacer = doc.add_paragraph()
    atbl._p.addnext(spacer._p)
    fmt(spacer, after=6)

    # ---- walk paragraphs
    h1 = h2 = 0
    paras = list(doc.paragraphs)
    abstract_seen = False
    keywords_par = None
    for p in paras:
        if p._p is title_par._p or p._p is spacer._p or p._p is sub._p:
            continue
        sty = p.style.name
        text = p.text.strip()
        if sty == "Title":
            p._p.getparent().remove(p._p)
            continue
        if sty == "Abstract Title" or (sty.startswith("Abstract") and text == "Abstract"):
            p._p.getparent().remove(p._p)
            continue
        if sty == "Abstract" and not abstract_seen:
            abstract_seen = True
            words = p.text
            clear_runs(p)
            r1 = p.add_run("Abstract: ")
            set_font(r1, size=9, bold=True, italic=True)
            r2 = p.add_run(words)
            set_font(r2, size=9, bold=True)
            fmt(p, size=9, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=4, indent=Inches(0.14))
            for r in p.runs[1:]:
                r.font.bold = True
            continue
        if text.startswith("KEYWORDS"):
            nxt = p._p.getnext()
            p._p.getparent().remove(p._p)
            continue
        if sty.startswith("Heading 1"):
            starred = text in ("Reproducibility", "References")
            if not starred:
                h1 += 1
                h2 = 0
            clear_runs(p)
            run = p.add_run((f"{roman(h1)}. " if not starred else "") + text)
            set_font(run, size=10, small_caps=True)
            p.style = doc.styles["Normal"]
            fmt(p, size=10, align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=4)
            for r in p.runs:
                r.font.small_caps = True
            continue
        if sty.startswith("Heading 2"):
            h2 += 1
            clear_runs(p)
            run = p.add_run(f"{chr(64 + h2)}. {text}")
            set_font(run, size=10, italic=True)
            p.style = doc.styles["Normal"]
            fmt(p, size=10, align=WD_ALIGN_PARAGRAPH.LEFT, before=6, after=3)
            for r in p.runs:
                r.font.italic = True
            continue
        if sty.startswith("Heading") and text.startswith("KEYWORDS"):
            continue
        if text.startswith("EQNUM"):
            continue
        if text.startswith("TABLENOTE"):
            strip_prefix(p, "TABLENOTE")
            fmt(p, size=8, after=6)
            continue
        if sty in ("Image Caption", "Caption"):
            continue
        if sty in ("Table Caption",):
            continue
        if p._p.find(".//" + qn("m:oMathPara")) is not None:
            continue
        if p._p.find(".//" + qn("w:drawing")) is not None:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            continue
        if re.match(r"^\[\d+\] ", text):
            fmt(p, size=8, align=WD_ALIGN_PARAGRAPH.LEFT, after=2)
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.25)
            continue
        if text:
            fmt(p, size=10, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=0, indent=Inches(0.14))

    # keywords line: rebuild after abstract
    abs_p = next(p for p in doc.paragraphs if p.text.startswith("Abstract: "))
    kw_src = abs_p._p.getnext()
    while kw_src is not None and not kw_src.tag.endswith("}p"):
        kw_src = kw_src.getnext()
    kw = Paragraph(kw_src, abs_p._parent)
    words = kw.text
    clear_runs(kw)
    r1 = kw.add_run("Index Terms: ")
    set_font(r1, size=9, bold=True, italic=True)
    r2 = kw.add_run(words)
    set_font(r2, size=9, bold=True)
    fmt(kw, size=9, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=6, indent=Inches(0.14))
    for r in kw.runs:
        r.font.bold = True

    fmt(title_par, size=24, align=WD_ALIGN_PARAGRAPH.CENTER, after=12, line=1.0)
    title_par.paragraph_format.first_line_indent = Inches(0)
    for p in doc.paragraphs:
        if p._p.find(".//" + qn("w:hyperlink")) is not None:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    # title + authors single column; everything from the abstract on in two columns
    section_break_after(spacer, 1)
    body_sect = doc.sections[-1]._sectPr
    cols = body_sect.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        body_sect.append(cols)
    cols.set(qn("w:num"), "2")
    cols.set(qn("w:space"), "360")
    typ = body_sect.find(qn("w:type"))
    if typ is None:
        typ = OxmlElement("w:type")
        body_sect.insert(0, typ)
    typ.set(qn("w:val"), "continuous")

    # equations: number each display and centre it with a right-aligned number
    for p in list(doc.paragraphs):
        t = p.text.strip()
        m = re.match(r"^EQNUM(\d+)$", t)
        if not m:
            continue
        nxt = p._p.getnext()
        eqp = Paragraph(nxt, p._parent)
        para = nxt.find(qn("m:oMathPara"))
        if para is not None:
            omaths = para.findall(qn("m:oMath"))
            idx = list(nxt).index(para)
            nxt.remove(para)
            for o in omaths:
                nxt.insert(idx, o)
                idx += 1
        pPr = eqp._p.get_or_add_pPr()
        tabs = eqp.paragraph_format.tab_stops
        tabs.add_tab_stop(Inches(1.75), WD_TAB_ALIGNMENT.CENTER)
        tabs.add_tab_stop(Inches(3.45), WD_TAB_ALIGNMENT.RIGHT)
        first_math = nxt.find(qn("m:oMath"))
        tab_run = OxmlElement("w:r")
        tab_run.append(OxmlElement("w:tab"))
        first_math.addprevious(tab_run)
        end = eqp.add_run(f"\t({m.group(1)})")
        set_font(end, size=10)
        eqp.paragraph_format.space_before = Pt(3)
        eqp.paragraph_format.space_after = Pt(3)
        p._p.getparent().remove(p._p)

    # captions and floats
    tno = 0
    fno = 0
    for tbl in doc.tables:
        tno += 1
        table_borders(tbl)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        for row in tbl.rows:
            for cell in row.cells:
                for cp in cell.paragraphs:
                    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for r in cp.runs:
                        set_font(r, size=7 if len(tbl.columns) < 8 else 6.5)
                    cp.paragraph_format.space_after = Pt(0)
                    cp.paragraph_format.first_line_indent = Inches(0)
        set_table_widths(tbl)
        cap = tbl._tbl.getprevious()
        if cap is not None and cap.tag.endswith("}p") and Paragraph(cap, doc._body).style.name == "Table Caption":
            capp = Paragraph(cap, doc._body)
            words = capp.text.strip()
            clear_runs(capp)
            set_font(capp.add_run(f"TABLE {roman(tno)}"), size=8)
            capp.add_run().add_break()
            set_font(capp.runs[-1], size=8)
            rr = capp.add_run(words)
            set_font(rr, size=8, small_caps=True)
            capp.style = doc.styles["Normal"]
            fmt(capp, size=8, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=3)
            capp.runs[-1].font.small_caps = True
    for p in doc.paragraphs:
        if p.style.name in ("Image Caption", "Caption") and p._p.getprevious() is not None:
            fno += 1
            for r in p.runs:
                set_font(r, size=8)
            prefix_run(p, f"Fig. {fno}. ", size=8)
            p.style = doc.styles["Normal"]
            fmt(p, size=8, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=2, after=8)
    # image sizes: wide figures across both columns are shrunk to the column in Word
    for shape in doc.inline_shapes:
        ratio = shape.height / shape.width
        shape.width = COL_W
        shape.height = int(COL_W * ratio)

    # never leave an en or em dash in the wording (the IEEE labels "Abstract" and "Index Terms" excepted)
    for p in doc.paragraphs:
        t = p.text
        for lab in ("Abstract: ", "Index Terms: "):
            t = t.replace(lab, "")
        if "\u2013" in t or "\u2014" in t:
            sys.exit(f"Dash rule broken in Word text: {t[:80]}")

    out = os.path.join(PAPER, OUT_NAME + ".docx")
    doc.save(out)
    print("Wrote", out)


if __name__ == "__main__":
    main()
