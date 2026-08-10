"""Sequence-level BPTT distillation into the deployable recurrent net."""

from __future__ import annotations

import random

import numpy as np
import torch
import torch.nn.functional as F  # noqa: N812

from cop_worker.rl.recurrent_policy import RecurrentActorCritic


def train_sequence_distillation(
    network: RecurrentActorCritic,
    sequences: list[tuple[torch.Tensor, torch.Tensor]],
    updates: int,
    seed: int,
    learning_rate: float,
) -> dict:
    """Truncated full-episode BPTT behaviour cloning."""
    rng = random.Random(seed)
    optimizer = torch.optim.Adam(network.parameters(), lr=learning_rate)
    batch_size = min(32, len(sequences))
    losses: list[float] = []
    accuracies: list[float] = []
    network.train()
    for _update in range(updates):
        batch = rng.sample(sequences, batch_size)
        max_length = max(len(features) for features, _labels in batch)
        hidden: torch.Tensor | None = None
        step_losses: list[torch.Tensor] = []
        correct = examples = 0
        for step in range(max_length):
            active = [
                index for index, (features, _labels) in enumerate(batch) if step < len(features)
            ]
            if not active:
                continue
            # GRU state is maintained for the full padded batch.  Inactive rows
            # receive zeros and are ignored by the loss.
            input_size = batch[0][0].shape[1]
            inputs = torch.zeros((batch_size, input_size), dtype=torch.float32)
            labels = torch.zeros(batch_size, dtype=torch.long)
            active_mask = torch.zeros(batch_size, dtype=torch.bool)
            for index in active:
                features, target = batch[index]
                inputs[index] = features[step]
                labels[index] = target[step]
                active_mask[index] = True
            logits, _values, hidden = network(inputs, hidden)
            active_logits = logits[active_mask]
            active_labels = labels[active_mask]
            step_losses.append(F.cross_entropy(active_logits, active_labels))
            correct += int((active_logits.argmax(dim=1) == active_labels).sum().item())
            examples += len(active_labels)
        loss = torch.stack(step_losses).mean()
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
        optimizer.step()
        losses.append(float(loss.item()))
        accuracies.append(correct / examples)
    network.eval()
    return {
        "mean_loss_last_50": float(np.mean(losses[-50:])),
        "mean_accuracy_last_50": float(np.mean(accuracies[-50:])),
        "updates": updates,
        "sequences": len(sequences),
        "examples": sum(len(features) for features, _labels in sequences),
    }
