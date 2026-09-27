#!/usr/bin/env python3
"""Write dist/arxiv_metadata.txt (title, plain-text abstract, categories) from paper/main.tex."""
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
s = (ROOT / "paper" / "main.tex").read_text()
ab = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", s, re.S).group(1)
t = ab.replace("\\%", "%").replace("``", '"').replace("''", '"').replace("$", "").replace("{", "").replace("}", "")
t = re.sub(r"\s+", " ", t).strip()
assert "\\" not in t, t
import subprocess
pages = subprocess.run(["pdfinfo", str(ROOT / "dist" / "main.pdf")], capture_output=True, text=True).stdout.split("Pages:")[1].split()[0]
n_tab = s.count("\\begin{table}"); n_fig = s.count("\\begin{figure}")
out = f"""arXiv submission metadata

Title:
Engineering Serendipity in Personal Agents: A Pre-registered Fifteen-Year Single-Subject Test of Exploitation versus Exploration

Authors:
Carl Kho

Abstract ({len(t)} characters; arXiv limit 1,920):
{t}

Comments:
{pages} pages, {n_fig} figures, {n_tab} tables. Pre-registration, code and aggregate results: https://github.com/CarlKho-Minerva/arxiv-Engineering-Serendpity (tag annotation-v1)

Primary category: cs.LG (Machine Learning)
Cross-lists: cs.IR (Information Retrieval), cs.HC (Human-Computer Interaction)

License: your choice at submission (CC BY 4.0 is the common default)

Upload file: dist/arxiv_bundle.tar.gz (main.tex, main.bbl, tables/, figures/)
"""
(ROOT / "dist" / "arxiv_metadata.txt").write_text(out)
print(len(t))
