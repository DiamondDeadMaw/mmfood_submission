import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.optim as optim
from sklearn.metrics import accuracy_score, roc_auc_score
from torch.nn import BCEWithLogitsLoss
from torch.utils.data import DataLoader, Dataset, random_split
from tqdm import tqdm

from Models.suspicious_ingredient.model import INPUT_DIM, SetTransformerForClassification


class IngredientBelongingDataset(Dataset):
    def __init__(self, labeled_examples, embeddings):
        self.labeled_examples = labeled_examples
        self.embeddings = embeddings

    def __len__(self):
        return len(self.labeled_examples)

    def __getitem__(self, idx):
        pairs = self.labeled_examples[idx]
        embs = [self.embeddings[ing] for ing, _ in pairs if ing in self.embeddings]
        labels = [label for ing, label in pairs if ing in self.embeddings]

        if not embs:
            return torch.empty(0, INPUT_DIM), torch.empty(0, dtype=torch.float)

        return torch.stack(embs), torch.tensor(labels, dtype=torch.float)


def collate(batch):
    batch = [item for item in batch if item[0].nelement() > 0]
    if not batch:
        return torch.empty(0, 0, INPUT_DIM), torch.empty(0, 0, dtype=torch.bool), torch.empty(0, 0, dtype=torch.float)

    embeddings, labels = zip(*batch)
    lengths = [e.size(0) for e in embeddings]
    max_len = max(lengths)
    batch_size = len(embeddings)

    padded_embeddings = torch.zeros(batch_size, max_len, INPUT_DIM)
    padded_labels = torch.full((batch_size, max_len), -1.0, dtype=torch.float)
    padding_mask = torch.ones(batch_size, max_len, dtype=torch.bool)

    for i, (emb, lbl) in enumerate(zip(embeddings, labels)):
        n = lengths[i]
        padded_embeddings[i, :n] = emb
        padded_labels[i, :n] = lbl
        padding_mask[i, :n] = False

    return padded_embeddings, padding_mask, padded_labels


def train(data_path, embedding_path, output_path, batch_size=32, epochs=30, lr=1e-5, val_split=0.1,
          weight_decay=1e-4, device_str="cuda"):
    device = torch.device(device_str if torch.cuda.is_available() else "cpu")

    with open(data_path, "r", encoding="utf-8") as f:
        examples = json.load(f)

    raw_embeddings = torch.load(embedding_path, map_location="cpu")
    embeddings = {k: v.float().cpu() for k, v in raw_embeddings.items()}

    val_size = int(len(examples) * val_split)
    train_examples, val_examples = random_split(
        examples, [len(examples) - val_size, val_size], generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(
        IngredientBelongingDataset(list(train_examples), embeddings),
        batch_size=batch_size, shuffle=True, collate_fn=collate,
    )
    val_loader = DataLoader(
        IngredientBelongingDataset(list(val_examples), embeddings),
        batch_size=batch_size, shuffle=False, collate_fn=collate,
    )

    model = SetTransformerForClassification().to(device)
    opt = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    total_pos = sum(1 for ex in train_examples for _, lbl in ex if lbl == 1)
    total_neg = sum(1 for ex in train_examples for _, lbl in ex if lbl == 0)
    criterion = BCEWithLogitsLoss(pos_weight=torch.tensor([total_pos / max(1, total_neg)], device=device))

    best_val_loss = float("inf")
    for epoch in range(1, epochs + 1):
        model.train()
        total_train_loss, train_count = 0.0, 0

        for embs, mask, labels in tqdm(train_loader, desc=f"Epoch {epoch}/{epochs} [train]"):
            if embs.nelement() == 0:
                continue

            embs, mask, labels = embs.to(device), mask.to(device), labels.to(device)
            opt.zero_grad()
            logits = model(embs, mask)
            active = ~mask
            loss = criterion(logits[active].squeeze(-1), labels[active])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

            total_train_loss += loss.item() * labels[active].size(0)
            train_count += labels[active].size(0)

        scheduler.step()
        avg_train_loss = total_train_loss / train_count if train_count else 0

        model.eval()
        total_val_loss, val_count = 0.0, 0
        all_true, all_probs = [], []
        with torch.no_grad():
            for embs, mask, labels in tqdm(val_loader, desc="[val]", leave=False):
                embs, mask, labels = embs.to(device), mask.to(device), labels.to(device)
                logits = model(embs, mask)
                active = ~mask
                loss = criterion(logits[active].squeeze(-1), labels[active])
                total_val_loss += loss.item() * labels[active].size(0)
                val_count += labels[active].size(0)
                all_probs.extend(torch.sigmoid(logits[active].squeeze(-1)).cpu().numpy())
                all_true.extend(labels[active].cpu().numpy())

        avg_val_loss = total_val_loss / val_count if val_count else float("inf")
        all_preds = (np.array(all_probs) > 0.5).astype(int)
        val_acc = accuracy_score(all_true, all_preds)
        val_auc = roc_auc_score(all_true, all_probs) if len(set(all_true)) > 1 else 0

        print(f"Epoch {epoch}: train_loss={avg_train_loss:.4f} val_loss={avg_val_loss:.4f} acc={val_acc:.4f} auc={val_auc:.4f}")

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save(model.state_dict(), output_path)
            print(f"Saved best model to {output_path}")

    print(f"Training complete. Best val loss: {best_val_loss:.6f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--embeddings", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--lr", type=float, default=1e-5)
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    train(args.data, args.embeddings, args.output, batch_size=args.batch_size, epochs=args.epochs, lr=args.lr)


if __name__ == "__main__":
    main()
