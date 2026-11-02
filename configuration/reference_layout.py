"""Filesystem layout of the reference workstation the configuration defaults describe.

Every absolute path default under ``configuration/`` lives below one of the roots
named here. The machine profile written by the installer rebases those roots onto
the current machine, so a new installation never edits a dataclass default.
"""

from __future__ import annotations

from pathlib import Path


class ReferenceLayout:
    """Roots of the DLR server layout that the configuration defaults are written against.

    Attributes:
        USER_ROOT     : Home of the reference user on the DLR server.
        CAMPAIGN_ROOT : Root under which the raw F-SAR campaign data lives.
        DATA_ROOT     : Directory holding every preprocessed dataset.
        PYRAT_DIR     : PyRAT checkout the processing workers import.
        REPO_ROOT     : Checkout of this repository on the reference machine.
        RUNS_ROOT     : Root of the run-output tree.
        RESULTS_ROOT  : Root of the analysis outputs.
        DATASET_DIR   : Preprocessed scene every training default points at.
        PARAMS_RUN    : Name of the Gaussian parameter-extraction run inside that scene.
        PARAMETERS    : Parameter array of that run.
        FUSAR_PROJECT : F-SAR project CSV describing the campaign stack.
    """

    USER_ROOT     = Path("/ste/rnd/User/vice_vi")
    CAMPAIGN_ROOT = "/ste/rnd/"
    DATA_ROOT     = USER_ROOT / "Dataset"
    PYRAT_DIR     = USER_ROOT / "pyrat"
    REPO_ROOT     = USER_ROOT / "DLR-TomoSAR"
    RUNS_ROOT     = REPO_ROOT / "runs"
    RESULTS_ROOT  = REPO_ROOT / "results"
    DATASET_DIR   = DATA_ROOT / "17sartom-traun_L_az1000-16000_rg500-4000_w26_12_hv_1_20260714_195834"
    PARAMS_RUN    = "params_k2_lam0_sig4_sigma_mu_amp"
    PARAMETERS    = DATASET_DIR / "params" / PARAMS_RUN / "parameters.npy"
    FUSAR_PROJECT = Path("/ste/rnd/User/sera_se/17sartom-traun_L.csv")


class ReferenceCluster:
    """LRZ Terrabyte account and cluster roots of the reference user.

    The machine profile's ``terrabyte`` section replaces these; without a profile
    the console submits exactly as the reference machine does.

    Attributes:
        USER         : LRZ user id the jobs are submitted under.
        HOME         : Home directory of that user on the cluster.
        SCRATCH      : Scratch directory of that user on the cluster.
        MODULE_TREE  : Modulefile tree providing micromamba on the login node.
        ENV_NAME     : micromamba environment the jobs run in.
        REMOTE_REPO  : Checkout of this repository in the cluster home.
        REMOTE_TREES : Directory holding one git worktree per submitted commit.
        REMOTE_LOGS  : Directory the sbatch scripts and job output land in.
        REMOTE_RUNS  : Scratch root the cluster runs are written into.
        REMOTE_DATA  : Scratch root holding the datasets.
    """

    USER         = "di24lot"
    HOME         = "/dss/dsshome1/0B/di24lot"
    SCRATCH      = "/dss/dsstbyfs02/scratch/0B/di24lot"
    MODULE_TREE  = "/dss/dsstbyfs01/pn56su/pn56su-dss-0020/usr/share/modules/files/"
    ENV_NAME     = "Dune"
    REMOTE_REPO  = f"{HOME}/DLR-TomoSAR"
    REMOTE_TREES = f"{HOME}/tomosar-worktrees"
    REMOTE_LOGS  = f"{HOME}/DLR-TomoSAR/logs/terrabyte"
    REMOTE_RUNS  = f"{SCRATCH}/runs"
    REMOTE_DATA  = f"{SCRATCH}/Dataset"
