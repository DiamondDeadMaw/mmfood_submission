import argparse

import torch
from datasets import load_dataset
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments

BASE_MODEL = "microsoft/deberta-v3-large"
ENTITY_MARKERS = ['[E1]', '[/E1]', '[E2]', '[/E2]']


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = logits.argmax(axis=-1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predictions, average='binary')
    return {
        'accuracy': accuracy_score(labels, predictions),
        'f1': f1,
        'precision': precision,
        'recall': recall,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--eval-batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    args = parser.parse_args()

    dataset = load_dataset('json', data_files=args.data, split='train')
    dataset = dataset.train_test_split(test_size=0.1, seed=42)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.add_special_tokens({'additional_special_tokens': ENTITY_MARKERS})

    def tokenize(examples):
        return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=256)

    tokenized_datasets = dataset.map(tokenize, batched=True)

    model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=2)
    model.resize_token_embeddings(len(tokenizer))

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        eval_strategy="steps",
        save_strategy="steps",
        save_steps=1000,
        save_total_limit=3,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        gradient_accumulation_steps=2,
        num_train_epochs=args.epochs,
        weight_decay=0.01,
        bf16=torch.cuda.is_available(),
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_dir=f"{args.output_dir}/logs",
        logging_steps=500,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["test"],
        compute_metrics=compute_metrics,
    )

    trainer.train()

    final_model_path = f"{args.output_dir}/finetuned_re_model"
    trainer.save_model(final_model_path)
    tokenizer.save_pretrained(final_model_path)
    print(f"Saved final model to {final_model_path}")


if __name__ == "__main__":
    main()
