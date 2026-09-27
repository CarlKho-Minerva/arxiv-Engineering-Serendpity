#!/usr/bin/env bash
# Build the arXiv upload bundle with plain pdflatex + bibtex (what arXiv runs), and fail loudly on
# undefined citations/references or LaTeX errors. Output: dist/arxiv_bundle.tar.gz and dist/main.pdf
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/Library/TeX/texbin:$PATH"
B="$(mktemp -d)"; trap 'rm -rf "$B"' EXIT
mkdir -p "$B/figures" "$B/tables" "$ROOT/dist"
cp "$ROOT/paper/main.tex" "$ROOT/paper/refs.bib" "$B/"
cp "$ROOT"/paper/tables/*.tex "$B/tables/"
for f in fig1_architecture fig2_counterfactual fig3_exploration_proxies fig4_preregistered; do cp "$ROOT/paper/figures/$f.pdf" "$B/figures/"; done
cd "$B"
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null || { tail -30 main.log; echo "FAIL: pdflatex pass 1"; exit 1; }
bibtex main >bibtex.out 2>&1 || { cat bibtex.out; echo "FAIL: bibtex"; exit 1; }
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
if grep -E "Citation .* undefined|Reference .* undefined|There were undefined" main.log; then echo "FAIL: undefined refs"; exit 1; fi
grep -iE "^Warning--" bibtex.out || true
grep -c "Overfull \\\\hbox" main.log | xargs -I{} echo "overfull hboxes: {}"
PAGES=$(pdfinfo main.pdf 2>/dev/null | awk '/Pages/{print $2}' || true); echo "pages: ${PAGES:-?}"
tar -czf "$ROOT/dist/arxiv_bundle.tar.gz" main.tex main.bbl tables figures
cp main.pdf "$ROOT/dist/main.pdf"; cp main.pdf "$ROOT/paper/main.pdf"
echo "OK: dist/arxiv_bundle.tar.gz ($(du -h "$ROOT/dist/arxiv_bundle.tar.gz" | cut -f1)), dist/main.pdf"
