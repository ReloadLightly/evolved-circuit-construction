"""Figures derived only from saved assessment/history data; no simulation."""

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .storage import read_json, write_text


def plot_saved(output):
    manifest = read_json(output / "manifest.json")
    cfg = manifest["config"]
    limit = cfg["output_mib"] * 1024**2
    plt.rcParams.update({"font.size": 9, "svg.hashsalt": "m1"})
    fig, axes = plt.subplots(1, len(cfg["seeds"]), figsize=(11, 3.3), squeeze=False)
    for col, seed in enumerate(cfg["seeds"]):
        ax = axes[0, col]
        for method in cfg["methods"]:
            path = output / f"{method}_{seed}/history.json"
            if not path.exists(): continue
            history = read_json(path)
            ax.plot([h["proposals"] for h in history], [h["best_training_loss"] for h in history], marker="o", label=method)
        ax.set(title=f"Seed {seed}", xlabel="Proposal slots", ylabel="Best training loss")
        ax.grid(alpha=0.2)
        ax.legend()
    fig.tight_layout()
    save(fig, output / "learning-curves.svg", output, limit)
    for method, seed in manifest["order"]:
        directory = output / f"{method}_{seed}"
        if not (directory / "assessment.json").exists(): continue
        assessment = read_json(directory / "assessment.json")
        fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=True)
        for col, split in enumerate(["dense_training", "interpolation"]):
            cases = assessment[split]["cases"]
            # Prespecified representative b: train 10 kHz, interpolation q=0.5.
            index = 2
            for row, case in enumerate(cases[index:index+2]):
                ax = axes[row, col]
                if not case["invalid"]:
                    ax.semilogx(case["frequency_hz"], case["amplitude"], color="tab:blue")
                low, high = sorted([case["f1"], case["f2"]])
                ax.axvspan(low, high, color="gray", alpha=0.15)
                ax.axhline(1, color="black", lw=0.6)
                ax.axhline(0.1, color="tab:red", ls=":", lw=0.8)
                ax.set(title=f"{split}: {case['mode']}, F1={case['f1']:.0f}, F2={case['f2']:.0f}\nloss={case['loss']:.4f}",
                       xlabel="Frequency (Hz)", ylabel="A = |Vout/Vsource| / 0.5", ylim=(-0.02, 1.05))
                ax.grid(alpha=0.2)
        fig.suptitle(f"{method}, seed {seed}: training-selected program")
        fig.tight_layout()
        save(fig, directory / "responses.svg", output, limit)
    print(f"Saved response and learning figures in {output}")


def save(fig, path, output, limit):
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", metadata={"Date": None})
    plt.close(fig)
    write_text(path, buffer.getvalue(), output, limit)
