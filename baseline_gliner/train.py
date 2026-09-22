import csv
import glob
import os
import re
from collections import defaultdict
import torch
from gliner import GLiNER
from gliner.data_processing.collator import SpanDataCollator
from gliner.training import Trainer, TrainingArguments


def carregar_dados():
    golden = defaultdict(list)
    for r in csv.DictReader(open("goldenset.csv", encoding="utf-8")):
        golden[r["documento_id"]].append({
            "inicio": int(r["inicio"]),
            "fim": int(r["fim"]),
            "tipo": r["tipo"],
            "trecho": r["trecho"],
        })

    def prepare_sections(text, anns):
        parts = []
        last = 0
        for m in re.finditer(r"\n\s*\n", text):
            parts.append((last, m.start()))
            last = m.end()
        parts.append((last, len(text)))

        chunks = []
        for p_start, p_end in parts:
            p_text = text[p_start:p_end]
            if len(p_text.strip()) < 5:
                continue

            tokens = []
            token_spans = []
            for tm in re.finditer(r"\S+", p_text):
                tokens.append(tm.group())
                token_spans.append((tm.start(), tm.end()))

            ner = []
            for a in anns:
                if a["inicio"] >= p_start and a["fim"] <= p_end:
                    rel_start = a["inicio"] - p_start
                    rel_end = a["fim"] - p_start

                    tok_start = None
                    tok_end = None
                    for tidx, (t0, t1) in enumerate(token_spans):
                        if tok_start is None and t1 > rel_start:
                            tok_start = tidx
                        if tok_start is not None and t0 < rel_end:
                            tok_end = tidx
                    if tok_start is not None and tok_end is not None:
                        if tok_start <= tok_end and (tok_end - tok_start) < 30:
                            ner.append([tok_start, tok_end, a["tipo"]])

            if len(ner) > 0 and len(tokens) <= 300:
                chunks.append({
                    "tokenized_text": tokens,
                    "ner": ner
                })
        return chunks

    train_data = []
    for path in sorted(glob.glob("txt/*.txt")):
        doc = os.path.splitext(os.path.basename(path))[0]
        txt = open(path, encoding="utf-8").read()
        anns = golden[doc]
        chunks = prepare_sections(txt, anns)
        train_data.extend(chunks)

    return train_data


def treinar(base_model="urchade/gliner_multi-v2.1", output_dir="models/gliner_jusbrasil", epochs=15, batch_size=4):
    train_data = carregar_dados()
    model = GLiNER.from_pretrained(base_model)
    collator = SpanDataCollator(model.config, data_processor=model.data_processor)

    training_args = TrainingArguments(
        output_dir=f"{output_dir}_ckpt",
        learning_rate=3e-5,
        others_lr=1e-5,
        per_device_train_batch_size=batch_size,
        num_train_epochs=epochs,
        weight_decay=0.01,
        logging_steps=50,
        save_strategy="no",
        report_to="none",
        bf16=torch.cuda.is_available(),
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_data,
        data_collator=collator,
    )

    trainer.train()
    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)


if __name__ == "__main__":
    treinar()
