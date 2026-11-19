"""Run and independently verify local rough-set and granular-ball studies."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

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


FROZEN_FILES = ('probe-plan.json', 'evidence.json', 'probe-result.json')
MANIFEST_VERSION = 2


def runner_fingerprint():
    return sha(Path(__file__).read_text(encoding='utf-8').encode('utf-8'))


def author_result(kind, evidence):
    if kind == 'math':
        status = 'refuted' if not evidence['lower_monotone'] else 'inconclusive'
        observation = ('The coarse lower contains 1 but the fine lower does not.' if status == 'refuted'
                       else 'The tested example does not establish the universal claim.')
        supported = ('This three-point covering is a counterexample to the stated lower inclusion.'
                     if status == 'refuted' else 'Only the recorded finite case was checked.')
        limitations = 'Uses the stated crisp covering operators; finite checks are not a general proof.'
    else:
        status = 'advance' if evidence['bound_met_on_all_splits'] else 'refuted'
        missed = [str(row['seed']) for row in evidence['runs'] if
                  100 * (row['point_correct'] - row['grain_correct']) > MAX_LOSS_PP * row['test_size']]
        observation = ('Seeds exceeding the prespecified loss bound: ' + ', '.join(missed) if missed
                       else 'All three splits satisfy the prespecified loss bound.')
        supported = ('The loss bound fails on the listed splits.' if missed
                     else 'The loss bound holds for the three recorded splits.')
        limitations = 'This is a compression proxy, not a GBSK reproduction or population estimate.'
    return dict(status=status, submitted_for_review=True, observation=observation,
                supported_claim=supported, limitations=limitations,
                next_step='Independently recompute and record the verdict.', artifacts=['evidence.json'])


def run_study(kind, folder):
    if folder.exists() or folder.is_symlink():
        raise ValueError('choose a new run directory; existing evidence is not overwritten')
    plan, calculate = study(kind)
    folder.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.workbench-', dir=folder.parent) as temp:
        staged = Path(temp) / 'run'
        staged.mkdir()
        dump(staged / 'probe-plan.json', plan)
        if call(staged, 'probe.py', 'plan', staged).returncode != 0:
            raise ValueError('invalid probe plan')
        evidence = calculate()
        dump(staged / 'evidence.json', evidence)
        dump(staged / 'probe-result.json', author_result(kind, evidence))
        dump(staged / 'run-manifest.json', dict(schema_version=MANIFEST_VERSION, study=kind,
             runner_sha256=runner_fingerprint(),
             files={name: sha((staged / name).read_bytes()) for name in FROZEN_FILES}))
        dump(staged / 'probe-review.json', dict(reviewer='', verdict='', evidence_artifact='evidence.json',
             evidence_location='', rival_check='', reason='', review_input_sha256=''))
        if folder.exists() or folder.is_symlink():
            raise ValueError('output path appeared during execution; existing evidence is not overwritten')
        staged.rename(folder)
    print(f'Run saved: {folder}')


def split_evidence(evidence):
    return {name: value for name, value in evidence.items() if name != 'environment'}, evidence.get('environment')


def verify(folder):
    manifest_path = folder / 'run-manifest.json'
    if not manifest_path.is_file():
        raise ValueError('run manifest missing; the run did not finish or is not a workbench run')
    manifest = read(manifest_path)
    if manifest.get('schema_version') != MANIFEST_VERSION:
        raise ValueError('legacy or unsupported manifest; preserve it and rerun in a new directory for this version')
    if manifest['runner_sha256'] != runner_fingerprint():
        raise ValueError('runner source differs (ignoring line endings); use the source version that produced this run')
    if set(manifest['files']) != set(FROZEN_FILES):
        raise ValueError('manifest does not enumerate the exact frozen files')
    for name in FROZEN_FILES:
        if manifest['files'][name] != sha((folder / name).read_bytes()):
            raise ValueError(f'frozen file changed: {name}')
    kind = manifest['study']
    if kind not in ('math', 'digits'):
        raise ValueError('unknown study in manifest')
    plan, calculate = study(kind)
    if read(folder / 'probe-plan.json') != plan:
        raise ValueError('recorded plan differs from the runner plan')
    recorded, before = split_evidence(read(folder / 'evidence.json'))
    recomputed, now = split_evidence(calculate())
    if before != now:
        print(f'workbench: environment differs (recorded {before}; current {now})', file=sys.stderr)
    if recorded != recomputed:
        raise ValueError('independent recomputation differs in scientific evidence')
    if read(folder / 'probe-result.json') != author_result(kind, recomputed):
        raise ValueError('author result differs from the recomputed evidence')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('math', 'digits', 'verify', 'review-input', 'check'))
    cli.add_argument('folder', type=Path)
    args = cli.parse_args()
    folder = args.folder.absolute()
    try:
        if args.mode in ('math', 'digits'):
            run_study(args.mode, folder)
        elif args.mode == 'verify':
            verify(folder)
            print('Recomputed evidence matches. No independent scientific verdict has been assigned.')
        else:
            verify(folder)
            return call(folder, 'probe.py', args.mode, folder).returncode
    except (ValueError, ImportError, OSError, KeyError) as exc:
        print(f'workbench: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
