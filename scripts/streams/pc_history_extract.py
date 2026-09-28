"""Parse every YouTube watch/search and Google Search history export in the Takeouts into JSONL (PC side).

Reads the zipped HTML in place (nothing extracted to disk). Output D:\\streams\\history\\{watch,yt_search,g_search}.jsonl
with {"ts": ISO local time + tz abbreviation, "text": title or query, "url", "channel", "export"} and a
sources.json saying which exports were readable (the Minerva export sits on F:, which may be offline).
Rows are deduplicated across exports by (ts, url or text).
"""
import html
import json
import os
import re
import zipfile
from datetime import datetime

# The second account's folder name contains an address, so it lives only in a local file on the PC (not in git).
_LOCAL = r"D:\streams\local_paths.json"
SECOND = json.load(open(_LOCAL))["second_account_takeout_dir"] if os.path.exists(_LOCAL) else r"F:\missing-local_paths.json"

SOURCES = [  # (zip, member) from the file catalog, 2026-09-27
    (r"D:\carlcrafters-takeout\takeout-20260820T180808Z-4-006.zip", "takeout-20260820/Takeout/YouTube and YouTube Music/history/watch-history.html", "watch"),
    (r"D:\carlcrafters-takeout-20260906\takeout-20260906T050316Z-5-013.zip", "Takeout/YouTube and YouTube Music/history/watch-history.html", "watch"),
    (r"D:\carlcrafters-takeout-20260915\takeout-20260915T025727Z-5-015.zip", "takeout-20260915/Takeout/YouTube and YouTube Music/history/watch-history.html", "watch"),
    (SECOND + r"\takeout-20260722T222739Z-1-001.zip", "takeout-minerva-20260722/Takeout/YouTube and YouTube Music/history/watch-history.html", "watch"),
    (r"D:\carlcrafters-takeout\takeout-20260820T180808Z-4-006.zip", "takeout-20260820/Takeout/YouTube and YouTube Music/history/search-history.html", "yt_search"),
    (r"D:\carlcrafters-takeout-20260906\takeout-20260906T050316Z-5-013.zip", "Takeout/YouTube and YouTube Music/history/search-history.html", "yt_search"),
    (r"D:\carlcrafters-takeout-20260915\takeout-20260915T025727Z-5-015.zip", "takeout-20260915/Takeout/YouTube and YouTube Music/history/search-history.html", "yt_search"),
    (r"D:\carlcrafters-takeout\takeout-20260820T180808Z-2-001.zip", "takeout-20260820/Takeout/My Activity/Search/MyActivity.html", "g_search"),
    (r"D:\carlcrafters-takeout-20260906\takeout-20260906T050316Z-2-001.zip", "Takeout/My Activity/Search/MyActivity.html", "g_search"),
    (r"D:\carlcrafters-takeout-20260915\takeout-20260915T025727Z-2-001.zip", "takeout-20260915/Takeout/My Activity/Search/MyActivity.html", "g_search"),
    (SECOND + r"\takeout-20260722T222739Z-2-001.zip", "takeout-minerva-20260722/Takeout/My Activity/Search/MyActivity.html", "g_search"),
]
OUT = r"D:\streams\history"
CELL = re.compile(r'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">(.*?)</div>', re.S)
A = re.compile(r'<a href="([^"]*)">(.*?)</a>', re.S)
DATE = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}\s?[AP]M)\s?([A-Z]{2,5})?")


def parse(text, kind, export):
    for cell in CELL.findall(text):
        plain = html.unescape(re.sub(r"<[^>]+>", "\n", cell)).replace("\u202f", " ").replace("\xa0", " ")
        head = plain.strip().split("\n", 1)[0]
        if kind == "watch" and not head.startswith("Watched"):
            continue
        if kind != "watch" and not head.startswith("Searched for"):
            continue
        links = A.findall(cell)
        m = DATE.search(plain)
        if not links or not m:
            continue
        try:
            ts = datetime.strptime(m.group(1).replace("  ", " "), "%b %d, %Y, %I:%M:%S %p")
        except ValueError:
            continue
        url, t = links[0][0], html.unescape(re.sub(r"<[^>]+>", "", links[0][1])).strip()
        yield {"ts": ts.isoformat(), "tz": m.group(2), "text": t, "url": url,
               "channel": html.unescape(re.sub(r"<[^>]+>", "", links[1][1])).strip() if kind == "watch" and len(links) > 1 else None,
               "export": export}


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = {"watch": {}, "yt_search": {}, "g_search": {}}
    used = []
    for z, member, kind in SOURCES:
        try:
            with zipfile.ZipFile(z) as zf:
                names = set(zf.namelist())
                m = member if member in names else member.split("/", 1)[1]  # catalog paths carry a store prefix
                text = zf.read(m).decode("utf-8", "replace")
        except Exception as e:
            used.append({"zip": z, "member": member, "kind": kind, "ok": False, "error": str(e)[:200]})
            continue
        n = 0
        for r in parse(text, kind, os.path.basename(z)):
            rows[kind].setdefault((r["ts"], r["url"] or r["text"]), r)
            n += 1
        used.append({"zip": z, "member": member, "kind": kind, "ok": True, "rows": n})
    for kind, d in rows.items():
        with open(os.path.join(OUT, f"{kind}.jsonl"), "w", encoding="utf-8") as fh:
            for r in sorted(d.values(), key=lambda r: r["ts"]):
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump({"sources": used, "unique": {k: len(v) for k, v in rows.items()}}, open(os.path.join(OUT, "sources.json"), "w"), indent=1)
    print(json.dumps({"unique": {k: len(v) for k, v in rows.items()}, "ok": sum(u["ok"] for u in used), "failed": [u["zip"][-40:] for u in used if not u["ok"]]}))


if __name__ == "__main__":
    main()
