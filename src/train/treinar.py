from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from challenge_jusbrasil.settings import MODELS, ROOT

ADAPTER_DIR = ROOT / "results" / "train" / "adapter"
LORA_R = 16
LORA_ALPHA = 16
EPOCHS = 1
LR = 2e-4
TREINO_MAX_LEN = 2048
MARCA_RESPOSTA = "<start_of_turn>model"


def modelo_aluno() -> dict[str, Any]:
    for modelo in MODELS:
        if "Qwen3-8B" in modelo["name"]:
            return modelo
    raise SystemExit("modelo Qwen3-8B ausente em settings")


def ler_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"jsonl ausente: {path}")
    linhas = []
    for linha in path.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            linhas.append(json.loads(linha))
    if not linhas:
        raise SystemExit(f"jsonl vazio: {path}")
    return linhas


def _tokenizar(tokenizer: Any, messages: list[dict[str, str]], max_len: int) -> dict[str, list[int]] | None:
    texto = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    resposta = messages[-1]["content"]
    pos = texto.rfind(resposta)
    if pos < 0:
        pos = texto.rfind(MARCA_RESPOSTA)
        if pos < 0:
            return None
        pos += len(MARCA_RESPOSTA)
    codificado = tokenizer(
        texto,
        truncation=False,
        return_offsets_mapping=True,
        add_special_tokens=False,
    )
    ids = list(codificado["input_ids"])
    mascara = list(codificado["attention_mask"])
    labels = [
        token if inicio >= pos else -100
        for token, (inicio, _) in zip(ids, codificado["offset_mapping"], strict=True)
    ]
    if len(ids) > max_len:
        ids = ids[-max_len:]
        mascara = mascara[-max_len:]
        labels = labels[-max_len:]
    if not any(rotulo != -100 for rotulo in labels):
        return None
    return {
        "input_ids": ids,
        "attention_mask": mascara,
        "labels": labels,
    }


def _lineares_bf16(modelo: Any) -> int:
    import torch
    import bitsandbytes as bnb

    trocas = [
        nome
        for nome, modulo in modelo.named_modules()
        if isinstance(modulo, bnb.nn.Linear4bit) and type(modulo.weight).__name__ != "Params4bit"
    ]
    for nome in trocas:
        pai_nome, _, filho = nome.rpartition(".")
        pai = modelo.get_submodule(pai_nome) if pai_nome else modelo
        modulo = getattr(pai, filho)
        novo = torch.nn.Linear(
            modulo.in_features,
            modulo.out_features,
            bias=modulo.bias is not None,
            device=modulo.weight.device,
            dtype=modulo.weight.dtype,
        )
        with torch.no_grad():
            novo.weight.copy_(modulo.weight)
            if modulo.bias is not None:
                novo.bias.copy_(modulo.bias)
        setattr(pai, filho, novo)
    return len(trocas)


def _carregar_modelo(nome: str) -> tuple[Any, Any]:
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(nome, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    config = AutoConfig.from_pretrained(nome, trust_remote_code=True)
    arquitetura = " ".join(config.architectures or [])
    classe = AutoModelForImageTextToText if "Gemma3" in arquitetura or "ConditionalGeneration" in arquitetura else AutoModelForCausalLM
    modelo = classe.from_pretrained(
        nome,
        device_map="auto",
        trust_remote_code=True,
    )
    convertidas = _lineares_bf16(modelo)
    print(f"camadas bf16 recolocadas={convertidas}", flush=True)
    modelo = prepare_model_for_kbit_training(modelo)
    campos: dict[str, Any] = {
        "r": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "lora_dropout": 0.0,
        "bias": "none",
        "task_type": "CAUSAL_LM",
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        "exclude_modules": ["vision_tower", "multi_modal_projector"],
    }
    try:
        ajuste = LoraConfig(**campos)
    except TypeError:
        campos.pop("exclude_modules")
        ajuste = LoraConfig(**campos)
    modelo = get_peft_model(modelo, ajuste)
    modelo.print_trainable_parameters()
    return modelo, tokenizer


def treinar(jsonl: Path, saida: Path = ADAPTER_DIR) -> Path:
    try:
        import torch
        from torch.utils.data import Dataset
        from transformers import Trainer, TrainingArguments
    except ImportError as exc:
        raise SystemExit("instale torch e transformers no ambiente de treino") from exc
    linhas = ler_jsonl(jsonl)
    aluno = modelo_aluno()
    modelo, tokenizer = _carregar_modelo(aluno["name"])

    class Conjunto(Dataset):
        def __init__(self) -> None:
            self.itens = []
            for linha in linhas:
                item = _tokenizar(tokenizer, linha["messages"], TREINO_MAX_LEN)
                if item is not None:
                    self.itens.append(item)

        def __len__(self) -> int:
            return len(self.itens)

        def __getitem__(self, indice: int) -> dict[str, list[int]]:
            return self.itens[indice]

    conjunto = Conjunto()
    if len(conjunto) == 0:
        raise SystemExit("nenhum exemplo coube no contexto de treino")
    print(f"exemplos de treino={len(conjunto)}", flush=True)
    saida.mkdir(parents=True, exist_ok=True)

    def agrupar(lote: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        return {
            "input_ids": torch.tensor([item["input_ids"] for item in lote], dtype=torch.long),
            "attention_mask": torch.tensor([item["attention_mask"] for item in lote], dtype=torch.long),
            "labels": torch.tensor([item["labels"] for item in lote], dtype=torch.long),
        }

    treinador = Trainer(
        model=modelo,
        args=TrainingArguments(
            output_dir=str(saida),
            num_train_epochs=EPOCHS,
            learning_rate=LR,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            warmup_steps=1,
            lr_scheduler_type="cosine",
            logging_steps=1,
            save_strategy="epoch",
            bf16=True,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            optim="paged_adamw_8bit",
            report_to="none",
            remove_unused_columns=False,
        ),
        train_dataset=conjunto,
        data_collator=agrupar,
    )
    treinador.train()
    modelo.save_pretrained(saida)
    tokenizer.save_pretrained(saida)
    print(f"adaptador salvo em {saida}", flush=True)
    return saida
