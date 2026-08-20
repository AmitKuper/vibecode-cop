"""Behavior-clone a student from teacher shards (episode-major, class-weighted).

Usage: python scripts/barrier_distill/train.py --arch gru --epochs 30 --out gru_v1.pt
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import torch  # noqa: E402

from barrier_distill.models import make_student  # noqa: E402
from cop_worker.rl.action_space import COP_ACTIONS  # noqa: E402

RESULTS = _REPO / "results" / "barrier_distill"
PLACE_IDS = {i for i, a in enumerate(COP_ACTIONS) if a.startswith("PLACE_")}


def load_shards(shards_dir: Path) -> list[dict]:
    episodes = []
    for shard in sorted(shards_dir.glob("shard_*.pt")):
        episodes.extend(torch.load(shard, map_location="cpu", weights_only=False)["episodes"])
    return episodes


def class_weights(episodes: list[dict]) -> torch.Tensor:
    counts = torch.ones(len(COP_ACTIONS))
    for ep in episodes:
        counts += torch.bincount(ep["labels"], minlength=len(COP_ACTIONS))
    weights = (counts.sum() / (len(COP_ACTIONS) * counts)).sqrt()
    return weights.clamp(1.0, 20.0)


def _epoch(net, episodes, weights, optimizer=None) -> dict:
    total, correct, loss_sum = 0, 0, 0.0
    place_hit, place_true, place_pred = 0, 0, 0
    for ep in episodes:
        feats, labels = ep["features"], ep["labels"]
        hidden, logits_seq = None, []
        for t in range(feats.shape[0]):
            logits, _v, hidden = net(feats[t : t + 1], hidden)
            logits_seq.append(logits)
        logits = torch.cat(logits_seq)
        loss = torch.nn.functional.cross_entropy(logits, labels, weight=weights)
        if optimizer is not None:
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
            optimizer.step()
        pred = logits.argmax(dim=1)
        total += len(labels)
        correct += int((pred == labels).sum())
        loss_sum += float(loss) * len(labels)
        for p, y in zip(pred.tolist(), labels.tolist(), strict=True):
            place_true += int(y in PLACE_IDS)
            place_pred += int(p in PLACE_IDS)
            place_hit += int(y in PLACE_IDS and p == y)
    return {
        "loss": loss_sum / max(1, total),
        "acc": correct / max(1, total),
        "place_recall": place_hit / max(1, place_true),
        "place_precision": place_hit / max(1, place_pred),
        "place_true": place_true,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", choices=["gru", "ff"], required=True)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    episodes = load_shards(RESULTS / "shards")
    rng = random.Random(args.seed)
    rng.shuffle(episodes)
    cut = max(1, len(episodes) // 10)
    val, train = episodes[:cut], episodes[cut:]
    weights = class_weights(train)
    input_size = train[0]["features"].shape[1]
    net = make_student(args.arch, input_size, len(COP_ACTIONS))
    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr)
    best = {"val_place_recall": -1.0}
    t0 = time.time()
    for epoch in range(args.epochs):
        rng.shuffle(train)
        net.train()
        tr = _epoch(net, train, weights, optimizer)
        net.eval()
        with torch.no_grad():
            va = _epoch(net, val, weights)
        score = va["place_recall"] + va["acc"]
        if score > best.get("score", -1):
            best = {"score": score, "epoch": epoch, **{f"val_{k}": v for k, v in va.items()}}
            torch.save(
                {
                    "arch": args.arch,
                    "input_size": input_size,
                    "n_actions": len(COP_ACTIONS),
                    "state_dict": net.state_dict(),
                    "train_stats": {"train": tr, "val": va, "epoch": epoch},
                    "episodes": len(train),
                },
                RESULTS / args.out,
            )
        print(
            f"[{args.arch}] epoch {epoch + 1}/{args.epochs} "
            f"train acc {tr['acc']:.3f} placeR {tr['place_recall']:.3f} | "
            f"val acc {va['acc']:.3f} placeR {va['place_recall']:.3f} "
            f"placeP {va['place_precision']:.3f} ({time.time() - t0:.0f}s)",
            flush=True,
        )
    print(f"[{args.arch}] BEST {best}", flush=True)


if __name__ == "__main__":
    main()
