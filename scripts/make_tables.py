#!/usr/bin/env python3
"""Write paper/tables/*.tex from results/paper_numbers.json so no number is hand-copied."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
N = json.loads((ROOT / "results" / "paper_numbers.json").read_text())
T = ROOT / "paper" / "tables"; T.mkdir(parents=True, exist_ok=True)


def fmt(x, nd=3):
    return f"{x:.{nd}f}".replace("-", "$-$")


def ci(c, nd=3):
    return f"[{fmt(c[0], nd)}, {fmt(c[1], nd)}]"


# ---- Table: sources
ex = N["exposures"]
msgs = {"msg_messenger": ("Facebook Messenger", 2610864, "2011"), "msg_telegram": ("Telegram", 363225, "2016"),
        "msg_instagram": ("Instagram DMs", 72345, "2017"), "msg_discord": ("Discord", 21622, "2020"),
        "msg_gmail": ("Gmail (3 accounts)", 6482, "2013"), "msg_linkedin": ("LinkedIn", 3104, "2020"),
        "msg_twitter": ("Twitter DMs", 2223, "2016"), "msg_gvoice": ("Google Voice", 2072, "2024"),
        "msg_gchat": ("Google Chat", 656, "2016")}
rows = []
for k, (name, n, y0) in msgs.items():
    rows.append(f"{name} & {y0} & {n:,} & {ex['by_source'][k]:,}\\\\")
tot = sum(v[1] for v in msgs.values())
(T / "sources.tex").write_text("\\begin{tabular}{lrrr}\\toprule\nSource & First year & Messages & Contact events\\\\\\midrule\n"
    + "\n".join(rows) + f"\n\\midrule\nTotal & & {tot:,} & {ex['n_exposures']:,}\\\\\\bottomrule\n\\end{{tabular}}\n")

# ---- Table: clone
c = N["clone"]; v = c["variants"]; vs = c["vs_A"]
lab = {"A": "A: immediate situation", "E": "E: all context layers, base model", "E-shuf": "E-shuf: shuffled context",
       "F": "F: random history", "L": "L: A + personal LoRA", "L+E": "L+E: all layers + personal LoRA"}
rows = [f"{lab['A']} & {fmt(v['A']['top1'])} & & & \\\\"]
for k in ("E", "E-shuf", "F", "L", "L+E"):
    d = vs[k]
    rows.append(f"{lab[k]} & {fmt(v[k]['top1'])} & {fmt(100*d['d_top1'],1)} & {ci([100*x for x in d['ci95_cluster_boot']],1)} & {d['days_with_gain']}/{d['days']}\\\\")
(T / "clone.tex").write_text("\\begin{tabular}{lrrrr}\\toprule\nVariant & Top-1 & $\\Delta$ vs.\\ A (pts) & 95\\% CI & Days with gain\\\\\\midrule\n"
    + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---- Table: pools
pp, ps = N["pool_primary"], N["pool_secondary"]
rows = []
for s, name in (("train", "Train (2011--2019)"), ("val", "Validation (2021--2022)"), ("test", "Test (2024--2025)")):
    rows.append(f"{name} & {pp[s]['candidates']:,} & {pp[s]['positives']:,} & {ps[s]['candidates']:,} & {ps[s]['positives']:,}\\\\")
(T / "pools.tex").write_text("\\begin{tabular}{lrrrr}\\toprule\n & \\multicolumn{2}{c}{Primary pool} & \\multicolumn{2}{c}{Secondary pool}\\\\\n"
    "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\nSplit & Exposures & Became lasting & Exposures & Became lasting\\\\\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---- Table: policies val/test, primary pool
names = [("relevance", "Relevance-only (reply model)"), ("ucb", "UCB (relevance + uncertainty)"), ("thompson", "Thompson sampling"),
         ("hybrid", "Hybrid exploration score"), ("epsilon_greedy", "$\\varepsilon$-greedy ($\\varepsilon=0.2$)"),
         ("random", "Random"), ("random_diversity", "Random with diversity budget"), ("novelty", "New-person-first (novelty)"),
         ("popularity", "Platform popularity$^\\dagger$")]
def policy_table(fv, ft, fname):
    V, Te = N[fv]["policies"], N[ft]["policies"]
    rows = [f"{n} & {fmt(V[k]['mrr'])} & {fmt(V[k]['recall@1'])} & {fmt(Te[k]['mrr'])} {ci(Te[k]['mrr_ci'],2)} & {fmt(Te[k]['recall@1'])}\\\\" for k, n in names]
    (T / fname).write_text("\\begin{tabular}{lrrrr}\\toprule\n & \\multicolumn{2}{c}{Validation 2021--2022} & \\multicolumn{2}{c}{Held-out test 2024--2025}\\\\\n"
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\nPolicy & MRR & recall@1 & MRR [95\\% CI] & recall@1\\\\\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
policy_table("metrics_val_primary", "metrics_test_primary", "policies_primary.tex")
policy_table("metrics_val_secondary_fullpool", "metrics_test_secondary_fullpool", "policies_secondary.tex")

# ---- Table: pre-registered decisions
def pr(f, key):
    d = N[f]["paired"][key]["mrr"]; return f"{fmt(d['diff'])} {ci(d['ci'])}"
hyp = [("H-PREM", "relevance $-$ random", "relevance-random", "CI $<0$"),
       ("H-SER", "hybrid $-$ random w/ diversity", "hybrid-random_diversity", "CI $>0$"),
       ("H-NOV", "novelty $-$ random w/ diversity", "novelty-random_diversity", "CI $>0$")]
def verdict(key):
    d = N["metrics_test_primary"]["paired"][key]["mrr"]; lo, hi = d["ci"]
    if key == "relevance-random": return "supported" if hi < 0 else ("rejected" if lo > 0 else "inconclusive")
    if key == "hybrid-random_diversity": return "supported" if lo > 0 else "rejected"
    return "supported" if lo > 0 else ("rejected" if hi < 0 else "inconclusive")
rows = [f"{h} & {desc} & {crit} & {pr('metrics_val_primary', k)} & {pr('metrics_test_primary', k)} & {pr('metrics_test_primary_permuted', k)} & \\textbf{{{verdict(k)}}}\\\\" for h, desc, k, crit in hyp]
(T / "prereg.tex").write_text("\\resizebox{\\linewidth}{!}{\\begin{tabular}{lllllll}\\toprule\nHypothesis & MRR difference & Supported if & Validation & Test & Test, labels permuted & Test verdict\\\\\\midrule\n"
    + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}}\n")

# ---- Table: judgments vs label
jl = N["judgments_vs_label"]
jn = [("p_invites_action", "Invites to an event, job, project or community"), ("p_org_or_group", "Written on behalf of an organization or group"),
      ("p_automated", "Automated, bulk or marketing"), ("ev_option_value", "Option-value score (0--3)"),
      ("p_exposure_type_social", "Type: personal or social chat")]
rows = [f"{n} & {fmt(jl['gemma'][k]['ordinary'],2)} & {fmt(jl['gemma'][k]['consequential'],2)} & {fmt(jl['gemma'][k]['auc'],2)} & {fmt(jl['qwen'][k]['ordinary'],2)} & {fmt(jl['qwen'][k]['consequential'],2)} & {fmt(jl['qwen'][k]['auc'],2)}\\\\" for k, n in jn]
(T / "judgments.tex").write_text("\\resizebox{\\linewidth}{!}{\\begin{tabular}{lrrrrrr}\\toprule\n & \\multicolumn{3}{c}{Gemma 4 31B} & \\multicolumn{3}{c}{Qwen3-8B}\\\\\n"
    "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\nJudgment & Ordinary & Became lasting & AUC & Ordinary & Became lasting & AUC\\\\\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}}\n")
print("tables:", sorted(p.name for p in T.glob("*.tex")))
print({h: verdict(k) for h, _, k, _ in hyp})
