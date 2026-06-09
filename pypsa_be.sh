#!/bin/bash
#SBATCH --job-name=pypsa_be
#SBATCH --ntasks=1
#SBATCH --time=00:15:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G

cd $VSC_SCRATCH/pypsa-eur

$HOME/.pixi/bin/pixi run snakemake all --configfile config/test/config.overnight.yaml