"""Run and independently verify local rough-set and granular-ball studies."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parent / 'skills' / 'research-idea' / 'scripts'
SEEDS = (11, 29, 47)
MAX_LOSS_PP = 3


def dump(path, obj):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def approximation(blocks, target):
    low = frozenset().union(*(b for b in blocks if b <= target))
    up = frozenset().union(*(b for b in blocks if b & target))
    return low, up


def subsets(universe):
    return [frozenset(b) for k in range(len(universe) + 1) for b in itertools.combinations(universe, k)]


def canonical(blocks):
    return [sorted(b) for b in blocks]


def math_evidence():
    universe = (0, 1, 2)
    targets = subsets(universe)
    blocks = targets[1:]
    coverings = [list(c) for k in range(1, len(blocks) + 1)
                 for c in itertools.combinations(blocks, k) if frozenset().union(*c) == frozenset(universe)]
    parts = [c for c in coverings if sum(map(len, c)) == len(universe)]
    checked = 0
    for fine, coarse in itertools.product(parts, repeat=2):
        if not all(any(f <= c for c in coarse) for f in fine):
            continue
        for target in targets:
            fl, fu = approximation(fine, target)
            cl, cu = approximation(coarse, target)
            if not cl <= fl or not fu <= cu:
                raise ValueError('partition refinement regression')
            checked += 1
    coarse = [frozenset((0, 1)), frozenset((1, 2))]
    fine = [frozenset((0,)), frozenset((1, 2))]
    target = frozenset((0, 1))
    fl, fu = approximation(fine, target)
    cl, cu = approximation(coarse, target)
    return dict(universe=list(universe), target=sorted(target), partition_checks=checked,
                coarse=canonical(coarse), fine=canonical(fine),
                fine_blocks_subsets_of_coarse=all(any(f <= c for c in coarse) for f in fine),
                coarse_lower=sorted(cl), fine_lower=sorted(fl), coarse_upper=sorted(cu), fine_upper=sorted(fu),
                lower_monotone=cl <= fl,
                proof_partition='Each x in a coarse block C contained in X has its fine partition block F inside C, by disjointness. For the upper inclusion, a fine block meeting X lies inside a coarse block also meeting X.')


def experiment():
    import numpy as np
    import sklearn
    from sklearn.datasets import load_digits
    from sklearn.model_selection import train_test_split

    x, y = load_digits(return_X_y=True)
    raw_x, raw_y = x.astype('<i2'), y.astype('<i2')
    rows = []
    for seed in SEEDS:
        train, test = train_test_split(np.arange(len(y)), test_size=0.25, random_state=seed, stratify=y)
        centers = np.stack([x[train[y[train] == label]].mean(axis=0) for label in range(10)])
        # Seed fixed prototypes from training only, and use nearest-prototype membership.
        rng = np.random.default_rng(seed)
        chosen = train[rng.choice(len(train), 64, replace=False)]
        assign = ((x[test, None, :] - x[None, chosen, :]) ** 2).sum(axis=2).argmin(axis=1)
        point = ((x[test, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        proto = ((x[chosen, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        grain = proto[assign]
        truth = y[test]
        point_correct, grain_correct = int((point == truth).sum()), int((grain == truth).sum())
        rows.append(dict(seed=seed, test_size=len(test), point_correct=point_correct, grain_correct=grain_correct,
                         disagreements=int((grain != point).sum()),
                         loss_pp=round(100 * (point_correct - grain_correct) / len(test), 6),
                         test_indices=test.tolist(), prototype_indices=chosen.tolist(),
                         truth=truth.tolist(), point_predictions=point.tolist(), grain_predictions=grain.tolist()))
    pass_bound = all(100 * (r['point_correct'] - r['grain_correct']) <= MAX_LOSS_PP * r['test_size'] for r in rows)
    return dict(dataset='scikit-learn built-in digits, 1797 x 64, no download',
                data_sha256=sha(raw_x.tobytes() + raw_y.tobytes()),
                environment=dict(python=sys.version.split()[0], numpy=np.__version__, sklearn=sklearn.__version__),
                loss_bound_pp=MAX_LOSS_PP, bound_met_on_all_splits=pass_bound, runs=rows)


def study(kind):
    if kind == 'math':
        return dict(kind='theory', source_kind='anomaly', source='domain/definitions.md: crisp covering model',
                    question='Does block containment alone preserve lower approximation under refinement?',
                    core_claim='For all finite coverings, if each fine block is contained in some coarse block, then coarse lower is contained in fine lower for every target.',
                    rival='A point of a coarse block may be covered only by fine blocks lying in another coarse block.',
                    setup='Finite crisp coverings; lower is the union of all blocks fully contained in the target.',
                    control='Compare coarse and fine definitions on one universe and target; disjoint partitions as a separate positive control.',
                    advance_if='A general proof under the stated covering assumptions.',
                    stop_if='One in-scope counterexample.', budget_minutes=15), math_evidence
    return dict(kind='empirical', source_kind='transfer', source='domain/definitions.md: prototype-compression proxy',
                question='Does prototype compression meet the preselected 3 pp loss limit?',
                core_claim='On each of the three fixed held-out digits splits, replacing inputs by the nearest of 64 training prototypes loses at most 3 percentage points of accuracy.',
                rival='Prototype assignments can cross class decision boundaries; accuracy can fall even with fixed centers.',
                setup='75/25 stratified splits with seeds 11, 29, 47; fixed raw pixels, Euclidean distance, no tuning.',
                control='Same train/test indices and class centroids, point input versus nearest training prototype input.',
                advance_if='All three splits lose at most 3 percentage points.',
                stop_if='Any split loses strictly more than 3 percentage points.', budget_minutes=10), experiment


def call(run, script, *args):
    return subprocess.run([sys.executable, '-B', str(SKILL / script), *map(str, args)],
                          env=dict(os.environ, PYTHONUTF8='1', LAB_IDEAS=str(run.parent)), check=False)


def run_study(kind, folder):
    if folder.exists():
        raise ValueError('choose a new run directory; existing evidence is not overwritten')
    plan, calculate = study(kind)
    folder.mkdir(parents=True)
    dump(folder / 'probe-plan.json', plan)
    if call(folder, 'probe.py', 'plan', folder).returncode != 0:
        raise ValueError('invalid probe plan')
    evidence = calculate()
    dump(folder / 'evidence.json', evidence)
    dump(folder / 'run-manifest.json', dict(study=kind, runner_sha256=sha(Path(__file__).read_bytes()),
         files={name: sha((folder / name).read_bytes()) for name in ('probe-plan.json', 'evidence.json')}))
    dump(folder / 'probe-result.json', dict(status='advance', observation='Evidence produced; requests independent verdict.',
         supported_claim='Only the exact finite scope in the attached plan and evidence was evaluated.',
         limitations='Not novelty evidence. The empirical study is a compression proxy, not GBSK reproduction.',
         next_step='Independently recompute and record the verdict.', artifacts=['evidence.json', 'run-manifest.json']))
    dump(folder / 'probe-review.json', dict(reviewer='', verdict='', evidence_artifact='evidence.json',
         evidence_location='', rival_check='', reason='', review_input_sha256=''))
    print(f'Run saved: {folder}')


def verify(folder):
    manifest = read(folder / 'run-manifest.json')
    if manifest['runner_sha256'] != sha(Path(__file__).read_bytes()):
        raise ValueError('runner version differs')
    for name in ('probe-plan.json', 'evidence.json'):
        if manifest['files'][name] != sha((folder / name).read_bytes()):
            raise ValueError(f'file changed: {name}')
    plan, calculate = study(manifest['study'])
    if read(folder / 'probe-plan.json') != plan or read(folder / 'evidence.json') != calculate():
        raise ValueError('independent recomputation differs, including any recorded environment differences')
    print('Recomputed evidence matches. No scientific verdict has been assigned.')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('math', 'digits', 'verify', 'review-input', 'check'))
    cli.add_argument('folder', type=Path)
    args = cli.parse_args()
    folder = args.folder.resolve()
    try:
        if args.mode in ('math', 'digits'):
            run_study(args.mode, folder)
        elif args.mode == 'verify':
            verify(folder)
        else:
            verify(folder)
            sys.stdout.flush()
            return call(folder, 'probe.py', args.mode, folder).returncode
    except (ValueError, ImportError, OSError, KeyError) as exc:
        print(f'workbench: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
