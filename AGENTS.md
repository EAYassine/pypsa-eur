# PyPSA-Eur: AGENTS.md

## Project background

**PyPSA-Eur** is an open-source sector-coupled energy system model of the European energy system (full ENTSO-E area), covering power, transport, heating, biomass, industry, and agriculture. It is built from open data using a Snakemake workflow and uses the [PyPSA](https://pypsa.org) framework. The model is suitable for both planning (capacity expansion) and operational (dispatch) studies. It has two main modes, electricity-only and sector coupled.

## Current objective

This fork adapts PyPSA-Eur to use **custom pre-made atlite cutouts** with climate-change-adjusted weather data (e.g. CMIP6-derived ERA5-like datasets for future scenarios). The goal is to run energy system optimisations under future climate conditions for a study on energy systems under climate change. Work involves modifying the cutout retrieval/loading pipeline so the workflow can accept externally generated cutouts instead of building them from ERA5. We are targeting **overnight (greenfield)** foresight scenarios in both **electricity-only** and **sector-coupled** modes. Work also involves fixing bugs that arise when optimising with future-era timesteps (e.g. temporal mismatches, horizon handling), and may require supplying other future-projected datasets (load profiles, etc.) beyond just weather cutouts.

A `prepared_cutout_dir` config option has been added to the `atlite` section. When set (e.g. `atlite.prepared_cutout_dir: "cutouts/prepared"`), cutouts are loaded from `<prepared_cutout_dir>/<name>.nc` instead of the versioned data path, and the fetch/build rules are skipped. Place `.nc` files directly in that directory.

### HERA data year override

A `sector.hera_data_year` config option (default `null`) overrides the year(s) used for HERA river discharge and ambient temperature data. When set (e.g. `sector.hera_data_year: 2020`), only that year's data is retrieved and its time index is rebased to match the snapshot period. If snapshots span multiple years, the single year is tiled (replicated) across all snapshot years. When `null` (default), HERA years are derived from snapshot years as before.

This was added because the JRC HERA URLs (`dis.HERA{year}.nc`, `ta6_{year}.nc`) do not exist for future years (2030+), so a historical year must be used. The rebase+tile logic lives in `_rebase_and_tile_time()` in `scripts/build_surface_water_heat_potentials/build_river_water_heat_potential.py`.

### Custom atlite module registration

Prepared cutouts generated with a modified atlite version may have `module: custom` in their NetCDF global attributes. The standard atlite installation only registers modules `era5`, `sarah`, `gebco`, so `atlite.Cutout(path)` fails with `KeyError: np.str_('custom')` when loading such cutouts.

The fix is in `scripts/_helpers.py:1051-1057` — `load_cutout()` registers a minimal mock module in `atlite.datasets.modules` before constructing the `atlite.Cutout` object:

```python
from atlite.datasets import modules as datamodules
if "custom" not in datamodules:
    import types
    m = types.ModuleType("custom")
    m.crs = 4326          # matches WGS84 (EPSG:4326) coordinate system
    datamodules["custom"] = m
```

This is safe because atlite only reads `datamodules[m].crs` from existing (prepared) cutouts; the rest of the module interface (`features`, `retrieve_data`, etc.) is only used when *building* new cutouts via `cutout.prepare()`, which is never called for prepared cutouts. The check `"custom" not in datamodules` makes registration idempotent.

### Electricity demand: fixed-year rebase for future snapshots

When snapshots are future years (e.g. 2030), the `build_electricity_demand` rule crashes because all load data sources (OPSD, ENTSOE, NESO, synthetic) only cover historical years (up to ~2023). The `load.fixed_year` config option was already defined but was broken for future-year scenarios.

**Bug**: `scripts/build_electricity_demand.py:314` indexed synthetic load data with `snapshots` unconditionally → `KeyError` when 2030 timestamps don't exist in the data. The `fixed_year` rebase block at lines 323-334 also had an ordering bug: `load.loc[years].reindex(index=snapshots)` destroyed data because `.reindex()` matched exact timestamps across different years, then the year-`replace` on line 334 ran on NaN data.

**Fix** (`scripts/build_electricity_demand.py:308-337`):

1. Read `fixed_year` before the synthetic block so both branches can use it.
2. Synthetic supplementation uses `fixed_year` timestamps instead of `snapshots` when `fixed_year` is set.
3. `fixed_year` rebase order is corrected: **select → rebase year → reindex to snapshots** (instead of reindex-then-rebase).

```python
if fixed_year:
    years = slice(str(fixed_year), str(fixed_year))
    load = load.loc[years]
    load.index = load.index.map(lambda t: t.replace(year=snapshots.year[0]))
    load = load.reindex(index=snapshots)
else:
    years = slice(snapshots[0], snapshots[-1])
    load = load.loc[years].reindex(index=snapshots)
```

Set `load.fixed_year: 2019` (or another year with good coverage) in the config to use historical load data rebased to the snapshot year.

## Environment & orchestration

- **Package manager**: Pixi (conda-forge ecosystem). `pixi install` to set up, `pixi run <task>` to run tasks.
- **Workflow engine**: Snakemake >=9. Entrypoint is `Snakefile` at repo root. Rules live in `rules/*.smk`, scripts in `scripts/*.py`.
- **Config-driven**: All workflow parameters in `config/config.default.yaml`. Local overrides in `config/config.yaml` (gitignored). Config is validated at Snakefile load time by `scripts/lib/validation/config/`.

## Some commands

| Command | What it does |
|---|---|
| `pixi run unit-tests` | `pytest test` (unit tests only) |
| `pixi run integration-tests` | Runs multiple snakemake workflows with test configs |
| `pixi run all-tests` | Unit + integration + clean |
| `pixi run generate-config` | Regenerates `config.default.yaml` and `schema.default.json` from code |
| `pixi run build-docs html` | Build Sphinx docs |
| `pixi run reset` | Deletes all generated outputs (resources, results, logs, benchmarks) |
| `pixi run update-dags` | Regenerates workflow DAG images |
| `pixi run sync-locks` | Resync pixi lock + export conda env specs |

Run a single snakemake rule: `snakemake -call <rule_name> --configfile config/test/config.electricity.yaml`.

## Directory layout

```
Snakefile              — Workflow entrypoint. Includes rules/*.smk.
rules/                 — Snakemake rule files (collect, retrieve, build, solve, postprocess)
scripts/               — Python scripts called by Snakemake rules
scripts/_helpers.py    — Shared utilities: mock_snakemake, configure_logging, update_config_from_wildcards, etc.
scripts/lib/validation/ — Config schema validation (pydantic/pandera)
config/                — YAML configs + JSON schema
config/test/           — Test-specific configs (use HiGHS solver, small scale)
data/versions.csv      — Dataset registry (source, version, URL)
data/                  — Downloaded datasets
cutouts/               — Weather data cutouts
resources/             — Intermediate build artifacts
results/               — Final model outputs
```

## Running actual simulations on the cluster (SLURM)

This machine is a **university HPC cluster (VUB)**. All real (non-dry) PyPSA runs must be submitted as SLURM jobs — do **not** run snakemake directly on the login node.

### SLURM job templates

Two reference scripts exist in the repo root (adapt `--configfile` as needed):

| File | Scope | Time | CPUs | Memory | Config |
|---|---|---|---|---|---|
| `pypsa_be.sh` | Belgium-only (test) | 00:15:00 | 8 | 32G | `config/test/config.overnight.yaml` |
| `pypsa_eu.sh` | Europe-wide | 06:00:00 | 16 | 512G | default |

**Do not exceed these resource limits** — higher requests increase queue time unnecessarily.

### Workflow for running actual simulations

1. Create or adapt a shell script (pattern below), or reuse an existing one:
   ```bash
   #!/bin/bash
   #SBATCH --job-name=pypsa_be        # descriptive name
   #SBATCH --ntasks=1
   #SBATCH --time=00:15:00            # walltime
   #SBATCH --cpus-per-task=8
   #SBATCH --mem=32G

   cd $VSC_SCRATCH/pypsa-eur

   $HOME/.pixi/bin/pixi run snakemake -call all --configfile config/belgium_2030_custom.yaml
   ```

2. Submit: `sbatch <script.sh>`

3. Monitor the job until it finishes, fails, or times out:
   ```bash
   squeue -j <jobid>        # check status
   cat slurm-<jobid>.out    # check output
   cat logs/...             # check specific logs
   ```

## Conventions

- **Python**: PyPSA/PyPSA-Eur style (ruff rules: pyflakes + pycodestyle + isort + pydocstyle + pyupgrade). Docstrings required on public symbols (pydocstyle enforced). No `ANN` annotations (relaxed).
- **YAML**: 2-space indent, preserved quotes.
- **Snakemake**: `snakefmt` formatter.
- Always use the Gurobi solver, set `solver.name: gurobi` and `solver-options: gurobi-default`.
- Changing `data/versions.csv` entries changes which datasets are downloaded. Datasets are cached by (name, source, version).
