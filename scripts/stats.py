#!/usr/bin/env python3
"""Statistics for evals. Standard library only.

Subcommands:
  power       How many tasks to detect a difference (or the MDE at your n)
  interval    Wilson and Bayesian intervals for a pass rate
  compare     Paired comparison of two models on the same tasks
  passk       pass@k and pass^k from repeated trials
  saturation  Discriminative power left in a benchmark

Run any subcommand with --help for its arguments, or with --demo to see it
work on built-in example data.

Why these and not scipy: every one of these is a dozen lines, and the
reason evals skip them is friction, not difficulty.
"""

import argparse
import json
import math
import statistics
import sys
from itertools import combinations

# ---------------------------------------------------------------- utilities

def _z(p):
    """Inverse standard normal CDF (Acklam's rational approximation).

    Max absolute error ~1.15e-9, which is far beyond what any eval needs.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _load_scores(path):
    """Accept {task_id: score}, [score, ...], or {"results": {...}}."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {str(i): v for i, v in enumerate(data)}
    raise ValueError(f"{path}: expected a list or an object of task_id -> score")


# -------------------------------------------------------------------- power

def cmd_power(args):
    alpha, beta = 1 - args.confidence, 1 - args.power
    z_a, z_b = _z(1 - alpha / 2), _z(1 - beta)
    k_term = 0.0
    if args.trials_a:
        k_term += args.within_variance / args.trials_a
    if args.trials_b:
        k_term += args.within_variance / args.trials_b
    total_var = args.variance + k_term

    print(f"alpha={alpha:.3f}  power={args.power:.2f}  "
          f"between-question variance={args.variance:.4f}")
    if k_term:
        print(f"within-question variance contribution: {k_term:.4f}")
    print()

    if args.n:
        mde = (z_a + z_b) * math.sqrt(total_var / args.n)
        print(f"At n = {args.n} tasks:")
        print(f"  minimum detectable effect = {mde:.4f}  ({mde*100:.2f} percentage points)")
        print()
        print("  Differences smaller than this are not resolvable at this size.")
        print("  Put this number in the benchmark card.")
    else:
        n = ((z_a + z_b) ** 2 * total_var) / (args.delta ** 2)
        print(f"To detect a difference of {args.delta:.4f} ({args.delta*100:.2f} pp):")
        print(f"  n = {math.ceil(n)} tasks")
        print()
        print("  Repeating each task reduces only the within-question term, with an")
        print("  asymptotic variance floor of 2/3. More tasks beats more trials.")


# ----------------------------------------------------------------- interval

def cmd_interval(args):
    n, s = args.n, args.successes
    if not 0 <= s <= n:
        sys.exit("successes must be between 0 and n")
    p = s / n
    z = _z(1 - (1 - args.confidence) / 2)

    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    wilson = (max(0.0, centre - half), min(1.0, centre + half))

    # Beta(1+s, 1+n-s) posterior, equal-tailed interval by bisection on the CDF.
    a, b = 1 + s, 1 + n - s
    lo = _beta_ppf((1 - args.confidence) / 2, a, b)
    hi = _beta_ppf(1 - (1 - args.confidence) / 2, a, b)

    se_clt = math.sqrt(p * (1 - p) / n) if n else 0.0
    clt = (p - z * se_clt, p + z * se_clt)

    pct = int(args.confidence * 100)
    print(f"pass rate: {s}/{n} = {p:.4f}")
    print()
    print(f"  Wilson {pct}%       [{wilson[0]:.4f}, {wilson[1]:.4f}]   <- use this for binary scores")
    print(f"  Bayesian {pct}%     [{lo:.4f}, {hi:.4f}]   Beta({a}, {b}) posterior")
    print(f"  CLT {pct}%          [{clt[0]:.4f}, {clt[1]:.4f}]")
    if n < 300:
        print()
        print(f"  n = {n} is below a few hundred, where CLT intervals under-cover")
        print("  (~92.5% actual coverage at n=100) and collapse to zero width at 0% or 100%.")
    if s in (0, n):
        print()
        print("  All-pass or all-fail: the CLT interval is degenerate here and the")
        print("  Wilson/Bayesian intervals are the only meaningful ones.")


def _beta_ppf(q, a, b, tol=1e-10):
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def _beta_cdf(x, a, b):
    """Regularized incomplete beta via continued fraction (Lentz)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta) / a
    if x > (a + 1) / (a + b + 2):
        return 1 - _beta_cdf(1 - x, b, a)
    f, c, d = 1.0, 1.0, 0.0
    for i in range(300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2*m - 1) * (a + 2*m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2*m) * (a + 2*m + 1))
        d = 1 + num * d
        d = 1e-30 if abs(d) < 1e-30 else d
        d = 1 / d
        c = 1 + num / c
        c = 1e-30 if abs(c) < 1e-30 else c
        f *= c * d
        if abs(1 - c * d) < 1e-12:
            break
    return front * (f - 1)


# ------------------------------------------------------------------ compare

def cmd_compare(args):
    a = _load_scores(args.results_a)
    b = _load_scores(args.results_b)
    shared = sorted(set(a) & set(b))
    if not shared:
        sys.exit("No task IDs in common — paired comparison needs the same tasks.")
    dropped = (len(a) - len(shared)) + (len(b) - len(shared))

    xa = [float(a[k]) for k in shared]
    xb = [float(b[k]) for k in shared]
    d = [p - q for p, q in zip(xa, xb)]
    n = len(d)

    mean_a, mean_b = statistics.fmean(xa), statistics.fmean(xb)
    mean_d = statistics.fmean(d)
    z = _z(1 - (1 - args.confidence) / 2)

    if n < 2:
        sys.exit("Need at least 2 shared tasks.")
    se_d = math.sqrt(statistics.variance(d) / n)
    se_a = math.sqrt(statistics.variance(xa) / n)
    se_b = math.sqrt(statistics.variance(xb) / n)
    se_unpaired = math.sqrt(se_a**2 + se_b**2)

    try:
        corr = statistics.correlation(xa, xb)
    except statistics.StatisticsError:
        corr = float("nan")

    ci = (mean_d - z * se_d, mean_d + z * se_d)
    sig = ci[0] > 0 or ci[1] < 0
    p_two = 2 * (1 - _norm_cdf(abs(mean_d / se_d))) if se_d > 0 else 0.0

    pct = int(args.confidence * 100)
    print(f"paired over {n} shared tasks" + (f"  ({dropped} unmatched, dropped)" if dropped else ""))
    print()
    print(f"  A: {mean_a:.4f}    B: {mean_b:.4f}")
    print(f"  difference (A - B): {mean_d:+.4f}  ({mean_d*100:+.2f} pp)")
    print(f"  {pct}% CI: [{ci[0]:+.4f}, {ci[1]:+.4f}]")
    print(f"  p (two-sided, normal approx): {p_two:.4f}")
    print()
    print(f"  per-task correlation: {corr:.3f}")
    print(f"  SE paired {se_d:.4f}  vs unpaired {se_unpaired:.4f}"
          f"  ({(1 - se_d/se_unpaired)*100:.0f}% narrower)" if se_unpaired > 0 else "")
    print()
    print(f"  => {'SIGNIFICANT' if sig else 'NOT significant'} at {pct}%")
    if not sig:
        mde = z * 2 * se_d
        print(f"     MDE at this n is about {mde:.4f} ({mde*100:.2f} pp).")
    if n < 100:
        print()
        print(f"  n = {n}: the normal approximation is shaky here. For a headline")
        print("  claim, use a Bayesian interval on the difference instead.")


# -------------------------------------------------------------------- passk

def cmd_passk(args):
    with open(args.results) as f:
        data = json.load(f)
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    if isinstance(data, dict):
        trials = data
    else:
        sys.exit('Expected {"task_id": [1, 0, 1, ...], ...}')

    k = args.k
    pass_at, pass_pow, per_task = [], [], []
    for task, runs in sorted(trials.items()):
        n = len(runs)
        c = sum(1 for r in runs if float(r) >= args.threshold)
        if n < k:
            print(f"  warning: '{task}' has {n} trials, k={k} — skipped", file=sys.stderr)
            continue
        pa = 1 - (math.comb(n - c, k) / math.comb(n, k)) if n - c >= k else 1.0
        pk = (math.comb(c, k) / math.comb(n, k)) if c >= k else 0.0
        pass_at.append(pa)
        pass_pow.append(pk)
        per_task.append((task, c, n, pa, pk))

    if not pass_at:
        sys.exit(f"No task had at least k={k} trials.")

    mean_pa = statistics.fmean(pass_at)
    mean_pk = statistics.fmean(pass_pow)
    mean_p1 = statistics.fmean(c / n for _, c, n, _, _ in per_task)

    print(f"{len(per_task)} tasks, k = {k}")
    print()
    print(f"  {'pass@1 (mean per-trial rate)':<34}{mean_p1:.4f}")
    print(f"  {f'pass@{k} (at least one of {k})':<34}{mean_pa:.4f}")
    print(f"  {f'pass^{k} (all {k} succeed)':<34}{mean_pk:.4f}")
    print()
    print(f"  reliability gap (pass@{k} - pass^{k}): {mean_pa - mean_pk:.4f}")
    print("  A large gap means the agent is inconsistent rather than incapable.")
    print(f"  Report pass^{k} wherever a single failure counts as a failure.")

    if args.verbose:
        print()
        print(f"  {'task':<30} {'c/n':>8} {'pass@k':>8} {'pass^k':>8}")
        for task, c, n, pa, pk in per_task:
            print(f"  {task[:30]:<30} {f'{c}/{n}':>8} {pa:>8.3f} {pk:>8.3f}")


# --------------------------------------------------------------- saturation

def cmd_saturation(args):
    with open(args.scores) as f:
        data = json.load(f)
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    if not isinstance(data, dict):
        sys.exit('Expected {"model_name": score, ...}')

    ranked = sorted(((m, float(s)) for m, s in data.items()), key=lambda t: -t[1])
    k = min(args.top_k, len(ranked))
    if k < 2:
        sys.exit("Need at least 2 models.")

    spread = ranked[0][1] - ranked[k - 1][1]
    se_delta = args.se_delta
    if se_delta is None:
        p = statistics.fmean(s for _, s in ranked[:k])
        se_one = math.sqrt(max(p * (1 - p), 1e-12) / args.n)
        se_delta = math.sqrt(2) * se_one
        est = " (estimated from n and the top-k mean)"
    else:
        est = ""

    r_norm = spread / se_delta if se_delta > 0 else float("inf")
    s_index = math.exp(-(r_norm ** 2))

    for label, lo in (("very high", 0.9), ("high", 0.7), ("moderate", 0.3),
                      ("low", 0.01), ("very low", 0.0)):
        if s_index >= lo:
            band = label
            break

    print(f"top-{k} spread: {spread:.4f}  ({ranked[0][0]} {ranked[0][1]:.4f} "
          f"-> {ranked[k-1][0]} {ranked[k-1][1]:.4f})")
    print(f"SE of the difference: {se_delta:.4f}{est}")
    print()
    print(f"  R_norm   = {r_norm:.3f}")
    print(f"  S_index  = {s_index:.4f}   [{band}]")
    print()
    if s_index >= 0.7:
        print("  Top models are not reliably distinguishable. Either add harder")
        print("  items and raise resolution, or graduate this into a regression")
        print("  suite and build its successor.")
    elif s_index >= 0.3:
        print("  Discriminative power is eroding. Plan the next batch of harder")
        print("  items now, and define retirement criteria before you need them.")
    else:
        print("  Still discriminating among top models.")

    if max(s for _, s in ranked) > 0.9:
        print()
        print(f"  Note: top score is {ranked[0][1]:.3f} — also near the ceiling,")
        print("  which is saturation rather than mere stagnation.")


# --------------------------------------------------------------------- main

DEMOS = {
    "power": ["power", "--delta", "0.03", "--variance", "0.111"],
    "interval": ["interval", "--successes", "34", "--n", "50"],
    "passk": ["passk", "--results", "__demo__", "--k", "3"],
    "saturation": ["saturation", "--scores", "__demo__", "--n", "200"],
    "compare": ["compare", "--results-a", "__demo__", "--results-b", "__demo__"],
}


def _write_demo_files(tmpdir):
    import os
    import random
    random.seed(7)
    paths = {}
    trials = {f"task_{i:03d}": [1 if random.random() < (0.4 + 0.5 * (i % 5) / 5) else 0
                                for _ in range(5)] for i in range(25)}
    paths["trials"] = os.path.join(tmpdir, "trials.json")
    with open(paths["trials"], "w") as f:
        json.dump(trials, f)

    a, b = {}, {}
    for i in range(60):
        base = random.random()
        a[f"task_{i:03d}"] = 1 if base < 0.62 else 0
        b[f"task_{i:03d}"] = 1 if base < 0.55 else 0
    paths["a"] = os.path.join(tmpdir, "a.json")
    paths["b"] = os.path.join(tmpdir, "b.json")
    with open(paths["a"], "w") as f:
        json.dump(a, f)
    with open(paths["b"], "w") as f:
        json.dump(b, f)

    paths["models"] = os.path.join(tmpdir, "models.json")
    with open(paths["models"], "w") as f:
        json.dump({"model-a": 0.812, "model-b": 0.807, "model-c": 0.803,
                   "model-d": 0.799, "model-e": 0.796, "model-f": 0.71}, f)
    return paths


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--demo", action="store_true",
                   help="run every subcommand on built-in example data")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("power", help="sample size or minimum detectable effect")
    sp.add_argument("--delta", type=float, default=0.05, help="difference to detect")
    sp.add_argument("--n", type=int, help="if given, report the MDE at this n instead")
    sp.add_argument("--variance", type=float, default=0.111,
                    help="between-question variance of the paired difference (default 1/9)")
    sp.add_argument("--within-variance", type=float, default=0.0,
                    help="within-question sampling variance, if repeating trials")
    sp.add_argument("--trials-a", type=int, default=0)
    sp.add_argument("--trials-b", type=int, default=0)
    sp.add_argument("--power", type=float, default=0.8)
    sp.add_argument("--confidence", type=float, default=0.95)
    sp.set_defaults(func=cmd_power)

    si = sub.add_parser("interval", help="Wilson and Bayesian intervals")
    si.add_argument("--successes", type=int, required=True)
    si.add_argument("--n", type=int, required=True)
    si.add_argument("--confidence", type=float, default=0.95)
    si.set_defaults(func=cmd_interval)

    sc = sub.add_parser("compare", help="paired comparison of two models")
    sc.add_argument("--results-a", required=True, help="JSON: task_id -> score")
    sc.add_argument("--results-b", required=True)
    sc.add_argument("--confidence", type=float, default=0.95)
    sc.set_defaults(func=cmd_compare)

    sk = sub.add_parser("passk", help="pass@k and pass^k")
    sk.add_argument("--results", required=True, help="JSON: task_id -> [trial scores]")
    sk.add_argument("--k", type=int, default=3)
    sk.add_argument("--threshold", type=float, default=1.0,
                    help="score at or above which a trial counts as success")
    sk.add_argument("--verbose", action="store_true")
    sk.set_defaults(func=cmd_passk)

    ss = sub.add_parser("saturation", help="discriminative power left")
    ss.add_argument("--scores", required=True, help="JSON: model -> score")
    ss.add_argument("--n", type=int, default=100, help="benchmark size, for SE estimation")
    ss.add_argument("--se-delta", type=float, help="measured SE of the difference, if known")
    ss.add_argument("--top-k", type=int, default=5)
    ss.set_defaults(func=cmd_saturation)

    args = p.parse_args()

    if args.demo:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            paths = _write_demo_files(td)
            runs = [
                ("power (n for delta=0.03)", ["power", "--delta", "0.03"]),
                ("power (MDE at n=40)", ["power", "--n", "40"]),
                ("interval", ["interval", "--successes", "34", "--n", "50"]),
                ("interval (all pass)", ["interval", "--successes", "20", "--n", "20"]),
                ("compare", ["compare", "--results-a", paths["a"], "--results-b", paths["b"]]),
                ("passk", ["passk", "--results", paths["trials"], "--k", "3"]),
                ("saturation", ["saturation", "--scores", paths["models"], "--n", "200"]),
            ]
            for title, argv in runs:
                print("=" * 68)
                print(title)
                print("=" * 68)
                ns = p.parse_args(argv)
                ns.func(ns)
                print()
        return

    if not getattr(args, "func", None):
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
