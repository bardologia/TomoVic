"""Curated catalog of the project's pipelines shown in the web UI.

Each entry names a pipeline, the entry-point script that runs it, a short
description, and the ordered stages the pipeline moves through.
"""

from __future__ import annotations


class PipelineLibrary:
    """Static descriptions of every processing, training and analysis pipeline."""

    def collect(self) -> list[dict]:
        """Returns one descriptor per pipeline, each with key, script and stage list."""
        return [
            {
                "key"    : "processing",
                "name"   : "Processing (Tomogram + Interferograms)",
                "script" : "pre_process",
                "blurb"  : "Ingest raw F-SAR passes via PyRat into the Capon reference tomogram, the amplitude-weighted interferometric stack, and the per-pixel geometry field for the physics loss.",
                "stages" : ["Capon tomogram (PyRat)", "Interferogram formation", "Track baselines & geometry field", "Artifact registry & layout"],
            },
            {
                "key"    : "param",
                "name"   : "Parameter Extraction",
                "script" : "extract_params",
                "blurb"  : "Fit a K-Gaussian mixture per elevation profile to build the supervised parameter targets, with penalised model-order selection.",
                "stages" : ["Profile conditioning", "Prominence init (CPU)", "Adam mixture fit (JAX GPU)", "Penalised best-K", "Mean-sorted target and diagnostics"],
            },
            {
                "key"    : "dataset",
                "name"   : "Dataset (Loaders)",
                "script" : None,
                "blurb"  : "Turn processed artifacts into PyTorch DataLoaders, consumed directly by training.",
                "stages" : ["Crop and split", "Patch extraction", "Augmentation", "Normalization"],
            },
            {
                "key"    : "training",
                "name"   : "Training (Supervised backbone)",
                "script" : "train_backbone",
                "blurb"  : "Supervised backbone loop: one forward pass to per-pixel Gaussian parameters, a weight-normalised curve, parameter and optional physics loss, AdamW with warmup, cosine annealing and a two-phase loss curriculum, and best-epoch checkpointing.",
                "stages" : ["Curve reconstruction", "Composite loss", "AdamW step", "Schedule and curriculum", "Eval and checkpoint"],
            },
            {
                "key"    : "dual_train",
                "name"   : "Dual Trunks (Train)",
                "script" : "train_dual",
                "blurb"  : "Split the backbone into two independent trunks: one reads its slice of the input stack to place the Gaussians, the other reads its slice to gate which slots are occupied. The output layout, the loss catalog, the curriculum and the whole inference stack are the backbone's, so dual runs compare directly against backbone runs.",
                "stages" : ["Trunk input routing", "Two trunks", "Per-slot heads and existence gate", "Shared composite loss", "Three-group AdamW and checkpoint"],
            },
            {
                "key"    : "profile_ae_train",
                "name"   : "Profile AE (Train)",
                "script" : "train_profile_autoencoder",
                "blurb"  : "Self-supervised profile autoencoder: synthesise elevation curves from the Gaussian parameters, normalise, then train an encoder-decoder to reconstruct them through a low-dimensional bottleneck.",
                "stages" : ["Curve genesis", "Normalization", "Autoencode", "Reconstruction loss", "Optimiser step"],
            },
            {
                "key"    : "image_ae_train",
                "name"   : "Image AE (Train)",
                "script" : "train_image_autoencoder",
                "blurb"  : "Self-supervised 2D autoencoder that reconstructs the normalised input patch, trained with a single reconstruction loss and two-group AdamW.",
                "stages" : ["Encode", "Decode", "Reconstruction loss", "Optimiser step", "Eval and checkpoint"],
            },
            {
                "key"    : "jepa_train",
                "name"   : "JEPA (Latent train)",
                "script" : "train_jepa",
                "blurb"  : "Predict the profile autoencoder's latent embedding from the SAR input and match it to the encoder's target embedding of the GT curve, anchored by a decoder curve-reconstruction loss.",
                "stages" : ["Couple pretrained AE", "Predict embedding", "Target embedding", "Embedding + recon loss", "Optimise & diagnostics"],
            },
            {
                "key"    : "unrolled_train",
                "name"   : "Unrolled Physics (Train)",
                "script" : "train_unrolled",
                "blurb"  : "Train the gamma_net unrolled inversion: synthesise per-pixel coherence measurements from the GT Gaussian profiles through the exact kz steering operator, then learn the proximal-gradient iterations (steps, thresholds, 1D prox) that invert them back to elevation profiles.",
                "stages" : ["Render GT profiles", "Synthesise coherence", "Unrolled inversion", "Masked curve loss", "Optimise & checkpoint"],
            },
            {
                "key"    : "inference",
                "name"   : "Inference",
                "script" : "infer_backbone",
                "blurb"  : "Sliding-window prediction, overlap-add curve stitching and centrality-selected parameter stitching. Runs that predict curves instead of parameters have K Gaussians refit to each predicted curve, scored against the extraction floor measured on the GT curves, so they reach the same parameter analysis. Then the full metric suite, reduced-Capon and interferometric-consistency baselines, and report generation.",
                "stages" : ["Windowed predict", "Cube stitch", "Curve param extraction", "Metrics", "Reduced & consistency", "Report and figures"],
            },
            {
                "key"    : "profile_ae_infer",
                "name"   : "Profile AE (Infer)",
                "script" : "infer_profile_autoencoder",
                "blurb"  : "Replay a trained profile autoencoder over a split: re-synthesise the GT elevation profiles from their Gaussian parameters, encode each to a latent and decode it back, then persist embeddings and score the physical, shape, power and latent-health metrics.",
                "stages" : ["Load run & rebuild profiles", "Encode-decode reconstruct", "Persist embeddings", "Metric suite", "Report & figures"],
            },
            {
                "key"    : "image_ae_infer",
                "name"   : "Image AE (Infer)",
                "script" : "infer_image_autoencoder",
                "blurb"  : "Replay a trained image autoencoder over a split: encode each normalised patch to an embedding-normalised latent, decode and denormalise it, then score physical, normalised and per-channel reconstruction error plus latent-collapse diagnostics.",
                "stages" : ["Load AE run", "Encode-decode", "Denormalise & pool", "Reconstruction metrics", "Embeddings & report"],
            },
            {
                "key"    : "benchmark",
                "name"   : "Benchmark (Capacity-matched)",
                "script" : "benchmark",
                "blurb"  : "Fairly compare backbone architectures at equal capacity: scale every model to the reference parameter budget, size its batch to the VRAM budget under a real training probe, train and infer identically across a seed and loss-component grid, then aggregate and rank.",
                "stages" : ["Capacity match to reference", "Max-batch probe (real loss)", "Seed x loss sweep", "Train & infer each unit", "Aggregate & leaderboard"],
            },
            {
                "key"    : "cross_validate",
                "name"   : "Cross-Validation (K-fold)",
                "script" : "cross_validate",
                "blurb"  : "Guard-banded spatial K-fold cross-validation: partition the scene azimuth into folds, train one model per fold (optionally per seed), infer on held-out val and test bands, and aggregate metrics into cross-fold mean and std.",
                "stages" : ["Fold plan & guard", "Per-fold training", "Held-out inference", "Seed & cross-fold aggregate", "Report & summary"],
            },
            {
                "key"    : "tuning",
                "name"   : "Tuning",
                "script" : "tune",
                "blurb"  : "Optuna joint hyperparameter search: TPE density-ratio proposals with constant-liar parallelism and median pruning, distributed across GPUs and resumable in chunks.",
                "stages" : ["Search space", "Joint search (TPE)", "Trial and pruning", "Best-config export"],
            },
            {
                "key"    : "feed_tuner",
                "name"   : "Feed Tuner (DataLoader)",
                "script" : "tune_dataloader",
                "blurb"  : "Sweep DataLoader settings (batch size, workers, prefetch, pin-memory) against the real training workload to find the configuration that keeps the GPU fed.",
                "stages" : ["Feed target (real dataset + model)", "Batch x workers sweep", "Loader / ceiling / end-to-end probe", "Saturate & recommend", "Prefetch-pin refine & report"],
            },
        ]
