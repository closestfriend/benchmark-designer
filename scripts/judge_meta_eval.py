#!/usr/bin/env python3
"""Validate an LLM judge against human labels. Standard library only.

ABC item O.c.1 requires "documented or experimental evidence of the judge's
accuracy, self-consistency, and agreement with human." Most benchmarks report
raw agreement, which systematically overstates: across 21 judges and ~541,000
judgments, chance-corrected agreement ran 33.8-41.3 points BELOW raw agreement
on MT-Bench, mean 38.6. An "85% agreement" judge is often kappa ~0.45.

Usage
-----
  python -I judge_meta_eval.py --labels labels.csv
  python -I judge_meta_eval.py --self-test

Input CSV, header row required. Only `human` and `judge` are mandatory:

  item_id,human,judge,judge_swapped,judge_repeat,human2
  q001,A,A,A,A,A
  q002,B,A,B,A,B

  human          the reference label
  judge          the judge's verdict
  judge_swapped  (optional) verdict with the two candidates presented in the
                 opposite order -> position flip rate
  judge_repeat   (optional) a second identical-conditions run -> test-retest
  human2         (optional) a second human rater -> the agreement ceiling

Blank cells are treated as missing and skipped pairwise.
"""

import argparse
import csv
import math
import sys
from collections import Counter
from itertools import combinations


# ------------------------------------------------------------------ metrics

def raw_agreement(pairs):
    if not pairs:
        return float("nan")
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def cohens_kappa(pairs):
    """Chance-corrected agreement between two raters on nominal labels."""
    if not pairs:
        return float("nan")
    n = len(pairs)
    labels = sorted({x for pair in pairs for x in pair})
    po = raw_agreement(pairs)
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    if abs(1 - pe) < 1e-12:
        return float("nan")
    return (po - pe) / (1 - pe)


def krippendorff_alpha(units, level="nominal"):
    """Alpha over units, each a list of ratings (missing values already dropped).

    Handles any number of raters and missing data, which Cohen's kappa does not.
    Computed from the coincidence matrix, per Krippendorff's standard formulation.
    """
    usable = [u for u in units if len(u) >= 2]
    if not usable:
        return float("nan")

    values = sorted({v for u in usable for v in u})
    idx = {v: i for i, v in enumerate(values)}
    k = len(values)
    if k < 2:
        return float("nan")

    # Each unit contributes its ordered rater pairs, weighted 1/(m-1) so the
    # unit's total mass is m. combinations() + both orientations already covers
    # same-value pairs; adding them again would double-count agreement.
    coincidence = [[0.0] * k for _ in range(k)]
    for unit in usable:
        m = len(unit)
        for a, b in combinations(range(m), 2):
            i, j = idx[unit[a]], idx[unit[b]]
            coincidence[i][j] += 1.0 / (m - 1)
            coincidence[j][i] += 1.0 / (m - 1)

    n_total = sum(sum(row) for row in coincidence)
    if n_total <= 0:
        return float("nan")
    marginals = [sum(row) for row in coincidence]

    def delta(i, j):
        if level == "nominal":
            return 0.0 if i == j else 1.0
        if level == "ordinal":
            lo, hi = min(i, j), max(i, j)
            inner = sum(marginals[lo:hi + 1]) - (marginals[lo] + marginals[hi]) / 2
            return inner ** 2
        if level == "interval":
            return (float(values[i]) - float(values[j])) ** 2
        raise ValueError(f"unknown level: {level}")

    do = sum(coincidence[i][j] * delta(i, j) for i in range(k) for j in range(k))
    de = sum(marginals[i] * marginals[j] * delta(i, j)
             for i in range(k) for j in range(k) if i != j)
    if de == 0:
        return float("nan")
    return 1 - (n_total - 1) * do / de


def wilson(successes, n, confidence=0.95):
    if n == 0:
        return (float("nan"), float("nan"))
    z = 1.959963984540054 if abs(confidence - 0.95) < 1e-9 else _z(1 - (1 - confidence) / 2)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _z(p):
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def interpret_kappa(k):
    if math.isnan(k):
        return "undefined"
    for lo, label in ((0.81, "almost perfect"), (0.61, "substantial"),
                      (0.41, "moderate"), (0.21, "fair"), (0.0, "slight")):
        if k >= lo:
            return label
    return "worse than chance"


# -------------------------------------------------------------------- input

def read_labels(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{path} has no data rows")
    required = {"human", "judge"}
    missing = required - set(rows[0].keys())
    if missing:
        sys.exit(f"{path} is missing required column(s): {', '.join(sorted(missing))}")
    return rows


def column_pairs(rows, col_a, col_b):
    out = []
    for r in rows:
        a, b = (r.get(col_a) or "").strip(), (r.get(col_b) or "").strip()
        if a and b:
            out.append((a, b))
    return out


# ------------------------------------------------------------------- report

def analyze(rows, confidence=0.95):
    hj = column_pairs(rows, "human", "judge")
    if not hj:
        sys.exit("No rows with both a human and a judge label.")

    n = len(hj)
    agree = sum(1 for a, b in hj if a == b)
    raw = agree / n
    kappa = cohens_kappa(hj)
    alpha = krippendorff_alpha([[a, b] for a, b in hj])
    ci = wilson(agree, n, confidence)

    print(f"{n} items with both human and judge labels")
    print()
    print("  JUDGE vs HUMAN")
    print(f"    raw agreement        {raw:.4f}   {int(confidence*100)}% CI [{ci[0]:.4f}, {ci[1]:.4f}]")
    print(f"    Cohen's kappa        {kappa:.4f}   ({interpret_kappa(kappa)})")
    print(f"    Krippendorff alpha   {alpha:.4f}")
    print(f"    kappa deflation      {raw - kappa:.4f}  ({(raw - kappa)*100:.1f} pp)")
    print()
    if raw - kappa > 0.30:
        print("    Deflation above 30 pp is normal and is exactly why raw agreement")
        print("    must not be reported alone. Report kappa or alpha as the headline.")
    elif raw - kappa < 0.05:
        print("    Unusually small deflation. Check the label distribution — this")
        print("    usually means one label dominates, not that the judge is excellent.")

    dist = Counter(b for _, b in hj)
    total = sum(dist.values())
    top_label, top_n = dist.most_common(1)[0]
    print()
    print("    judge label distribution: " +
          ", ".join(f"{k}={v}" for k, v in sorted(dist.items())))
    if top_n / total > 0.8:
        print(f"    WARNING: '{top_label}' is {top_n/total:.0%} of verdicts — a constant")
        print("    judge would score similarly. Check against a constant baseline.")

    # ----- the human ceiling
    hh = column_pairs(rows, "human", "human2")
    if hh:
        hh_raw = raw_agreement(hh)
        hh_kappa = cohens_kappa(hh)
        print()
        print(f"  HUMAN vs HUMAN  ({len(hh)} doubly-labeled items)")
        print(f"    raw agreement        {hh_raw:.4f}")
        print(f"    Cohen's kappa        {hh_kappa:.4f}   ({interpret_kappa(hh_kappa)})")
        print()
        if not math.isnan(hh_kappa) and not math.isnan(kappa):
            ratio = kappa / hh_kappa if hh_kappa > 0 else float("nan")
            print(f"    judge kappa / human ceiling: {ratio:.2f}")
            if ratio >= 0.9:
                print("    The judge is about as good as a second human. Usable.")
            elif ratio >= 0.7:
                print("    Below the human ceiling but in range. Report both numbers")
                print("    and treat judge scores as noisier than human scores.")
            else:
                print("    Well below the human ceiling. Either the construct is not")
                print("    judge-measurable, the rubric is underspecified, or the human")
                print("    labels are inconsistent. All three are worth reporting.")
    else:
        print()
        print("  HUMAN vs HUMAN: no second rater supplied.")
        print("    Without a ceiling you cannot tell a bad judge from a hard construct.")
        print("    Double-label at least a subset.")

    # ----- position bias
    swapped = column_pairs(rows, "judge", "judge_swapped")
    if swapped:
        flips = sum(1 for a, b in swapped if a != b)
        rate = flips / len(swapped)
        print()
        print(f"  POSITION BIAS  ({len(swapped)} swapped pairs)")
        print(f"    flip rate            {rate:.4f}")
        print(f"    position consistency {1 - rate:.4f}")
        if rate > 0.2:
            print()
            print("    Flip rate above 20% means the ordering is driving a fifth of")
            print("    verdicts. Direction of position bias is model- and task-specific,")
            print("    so measure it; don't assume primacy.")
    else:
        print()
        print("  POSITION BIAS: no judge_swapped column.")
        print("    For pairwise judging this is not optional — run every item in")
        print("    both orders.")

    # ----- test-retest
    repeat = column_pairs(rows, "judge", "judge_repeat")
    if repeat:
        same = raw_agreement(repeat)
        print()
        print(f"  TEST-RETEST  ({len(repeat)} repeated items)")
        print(f"    self-consistency     {same:.4f}")
        if same > 0.95:
            print()
            print("    Above 0.95. Scrutinize position bias specifically: judges with")
            print("    0.99 test-retest have been measured carrying severe position")
            print("    bias. Stability measures the steadiness of the output, not the")
            print("    correctness of the decision process.")
        elif same < 0.85:
            print()
            print("    Below 0.85 at fixed conditions. Check the temperature and")
            print("    whether the rubric is ambiguous.")

    # ----- verdict
    print()
    print("=" * 70)
    issues = []
    if math.isnan(kappa) or kappa < 0.4:
        issues.append("kappa below 0.4 — agreement is weak once chance is removed")
    if not hh:
        issues.append("no human-human ceiling")
    if not swapped:
        issues.append("position bias unmeasured")
    if not repeat:
        issues.append("test-retest unmeasured")
    if top_n / total > 0.8:
        issues.append("judge verdicts are heavily skewed to one label")

    if issues:
        print("Not yet validated. Outstanding:")
        for i in issues:
            print(f"  - {i}")
        print()
        print("Until these are closed, the judge's contribution to any headline")
        print("number is unquantified. Say so in the card rather than letting the")
        print("decimal places imply otherwise.")
    else:
        print("Meta-evaluation complete. Report in the benchmark card:")
        print(f"  kappa {kappa:.3f} against a human ceiling of {cohens_kappa(hh):.3f}, "
              f"n={n}")
        print(f"  position flip rate {sum(1 for a, b in swapped if a != b)/len(swapped):.3f}, "
              f"test-retest {raw_agreement(repeat):.3f}")
        print("  judge model and version, sampling params, and the prompt verbatim")
    print("=" * 70)


def self_test():
    import random
    import tempfile
    import os
    random.seed(11)
    rows = [["item_id", "human", "judge", "judge_swapped", "judge_repeat", "human2"]]
    for i in range(200):
        truth = random.choice("AB")
        other = "B" if truth == "A" else "A"
        judge = truth if random.random() < 0.80 else other
        swapped = judge if random.random() < 0.88 else ("B" if judge == "A" else "A")
        repeat = judge if random.random() < 0.97 else ("B" if judge == "A" else "A")
        h2 = truth if random.random() < 0.86 else other
        rows.append([f"q{i:03d}", truth, judge, swapped, repeat, h2])

    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print("Self-test: 200 synthetic items, judge ~80% accurate against a ~86%")
    print("human-human ceiling, with mild position bias and high self-consistency.")
    print()
    analyze(read_labels(path))
    os.unlink(path)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--labels", help="CSV with human and judge columns")
    p.add_argument("--confidence", type=float, default=0.95)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        return self_test()
    if not args.labels:
        p.error("--labels is required (or use --self-test)")
    analyze(read_labels(args.labels), args.confidence)


if __name__ == "__main__":
    main()
