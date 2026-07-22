#!/bin/bash

#SLURM script to run the app_study.py script in a singularity container

#SBATCH --job-name=app_study
#SBATCH --output=app_study_%j.log
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --cpus-per-task=>1

apptainer run --bind /scratch:/scratch cim-apps.sif flows \
    --apk-list /scratch/corpus.txt --outdir /scratch/results \
    --bind /scratch/project/results:/output \
    --task-index "$SLURM_ARRAY_TASK_ID" --task-count 100