#!/usr/bin/env python3
"""Write paper/tables/*.tex from results/paper_numbers.json so no number is hand-copied."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
N = json.loads((ROOT / "results" / "paper_numbers.json").read_text())
T = ROOT / "paper" / "tables"; T.mkdir(parents=True, exist_ok=True)


def fmt(x, nd=3, keep_sign=False):
    t = f"{x:.{nd}f}"
    if t.startswith("-") and float(t) == 0 and not keep_sign:
        t = t[1:]
    return t.replace("-", "$-$")


def ci(c, nd=3, keep_sign=False):
    return f"[{fmt(c[0], nd, keep_sign)}, {fmt(c[1], nd, keep_sign)}]"


# ---- Table: sources (counts from paper_numbers.json)
ex = N["exposures"]; SRC = N["sources"]
names = {"msg_messenger": "Facebook Messenger", "msg_telegram": "Telegram", "msg_instagram": "Instagram DMs", "msg_discord": "Discord",
         "msg_gmail": "Gmail (3 accounts)", "msg_linkedin": "LinkedIn", "msg_twitter": "Twitter DMs", "msg_gvoice": "Google Voice", "msg_gchat": "Google Chat"}
rows = [f"{nm} & {SRC['first_year'][k]} & {SRC['messages'][k]:,} & {ex['by_source'][k]:,}\\\\" for k, nm in names.items()]
(T / "sources.tex").write_text("\\begin{tabular}{lrrr}\\toprule\nSource & First year & Messages & Contact events\\\\\\midrule\n"
    + "\n".join(rows) + f"\n\\midrule\nTotal & & {SRC['total']:,} & {ex['n_exposures']:,}\\\\\\bottomrule\n\\end{{tabular}}\n")

# ---- Table: clone
c = N["clone"]; v = c["variants"]; vs = c["vs_A"]
lab = {"A": "A: immediate situation", "C": "C: relevant personal history", "E": "E: all context layers, base model", "E-shuf": "E-shuf: shuffled context",
       "F": "F: random history", "L": "L: A + personal LoRA", "L+E": "L+E: all layers + personal LoRA"}
rows = [f"{lab['A']} & {fmt(v['A']['top1'])} & & & \\\\"]
for k in ("C", "F", "E", "E-shuf", "L", "L+E"):
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
         ("random", "Random"), ("random_diversity", "Random with diversity budget"), ("novelty", "New-thread-first (novelty)"),
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
rows = [f"{h} & {pr('metrics_val_primary', k)} & {pr('metrics_test_primary', k)} & {pr('metrics_test_primary_permuted', k)} & \\textbf{{{verdict(k)}}}\\\\" for h, desc, k, crit in hyp]
(T / "prereg.tex").write_text("\\begin{tabular}{lllll}\\toprule\nHypothesis & Validation & Test & Test, labels permuted & Verdict\\\\\\midrule\n"
    + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")

# ---- Table: judgments vs label, by period
jn = [("p_invites_action", "Invites to an event, job, project or community"), ("p_org_or_group", "Written on behalf of an organization or group"),
      ("p_automated", "Automated, bulk or marketing"), ("ev_option_value", "Option-value score (0--3)"),
      ("p_exposure_type_social", "Type: personal or social chat")]
def jtable(per, fname):
    J = N["judgments_by_period"][per]
    rows = [f"{n} & {fmt(J['gemma'][k]['ordinary'],2)} & {fmt(J['gemma'][k]['consequential'],2)} & {fmt(J['gemma'][k]['auc'],2)} & {fmt(J['qwen'][k]['ordinary'],2)} & {fmt(J['qwen'][k]['consequential'],2)} & {fmt(J['qwen'][k]['auc'],2)}\\\\" for k, n in jn]
    (T / fname).write_text("\\resizebox{\\linewidth}{!}{\\begin{tabular}{lrrrrrr}\\toprule\n & \\multicolumn{3}{c}{Gemma 4 31B} & \\multicolumn{3}{c}{Qwen3-8B}\\\\\n"
        "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\nJudgment & Ordinary & Became lasting & AUC & Ordinary & Became lasting & AUC\\\\\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}}\n")
jtable("dev", "judgments_dev.tex"); jtable("test", "judgments_test.tex")

# ---- Table: secondary endpoints (paired recall differences, test)
pairs = [("H-PREM", "relevance-random"), ("H-SER", "hybrid-random_diversity"), ("H-NOV", "novelty-random_diversity")]
rows = []
for pool, f in (("Primary", "metrics_test_primary"), ("Secondary", "metrics_test_secondary_fullpool")):
    for h, k in pairs:
        P = N[f]["paired"][k]
        rows.append(f"{pool} & {h} & " + " & ".join(f"{fmt(P[m]['diff'])} {ci(P[m]['ci'],3,True)}" for m in ("recall@1", "recall@3", "recall@5")) + "\\\\")
(T / "secondary_endpoints.tex").write_text("\\resizebox{\\linewidth}{!}{\\begin{tabular}{llrrr}\\toprule\nPool & Hypothesis & recall@1 & recall@3 & recall@5\\\\\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}}\n")

# ---- Macros for counts used in prose and captions
SW = N["scored_weeks"]; PP = N["pool_primary"]; PS = N["pool_secondary"]
def mac(name, val): return f"\\newcommand{{\\{name}}}{{{val}}}"
M = []
for pool, tag in (("primary", "P"), ("secondary", "S")):
    for sp, st in (("train", "Tr"), ("val", "Va"), ("test", "Te")):
        w = SW[pool][sp]; pl = (PP if pool == "primary" else PS)[sp]
        M += [mac(f"n{tag}{st}Exp", f"{pl['candidates']:,}"), mac(f"n{tag}{st}Pos", f"{pl['positives']:,}"),
              mac(f"n{tag}{st}Weeks", w["weeks_total"]), mac(f"n{tag}{st}Scored", w["weeks_scored"]),
              mac(f"n{tag}{st}ScoredExp", f"{w['exposures_scored']:,}"), mac(f"n{tag}{st}Median", f"{w['median_set_scored']:g}"),
              mac(f"n{tag}{st}Rate", f"{100*w['positive_rate']:.0f}")]
JD = N["judgments_by_period"]["dev"]["gemma"]
M += [mac("nDevJudged", f"{JD['n']:,}"), mac("nDevJudgedPos", f"{JD['positives']:,}")]
M += [mac("qwenAutoPct", f"{100*N['qwen_automated_share_weak']:.0f}"), mac("gemmaAutoPct", f"{100*N['automated_share_weak']:.1f}"),
      mac("aucPrimaryTest", f"{N['auc']['primary']['all'][1]:.3f}"), mac("aucSecondaryTest", f"{N['auc']['secondary']['all'][1]:.3f}")]
(T / "numbers.tex").write_text("\n".join(M) + "\n")

print("tables:", sorted(p.name for p in T.glob("*.tex")))
print({h: verdict(k) for h, _, k, _ in hyp})
