#!/bin/bash
#SBATCH --job-name=pypsa_eu
#SBATCH --ntasks=1
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=512G
#SBATCH --mail-type=BEGIN,END,FAIL --mail-user=yassine.el.alali@vub.be

cd $VSC_SCRATCH/pypsa-eur

$HOME/.pixi/bin/pixi run snakemake -call all