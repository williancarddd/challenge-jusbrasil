"""O servidor da LLM como subprocesso do pipeline — sem container.

O vLLM entra como dependência do projeto e é subido pelo próprio `main.py`, que o
derruba ao terminar. `extraction.py` continua falando HTTP com `localhost:8000`, então o
caminho medido não muda: só quem sobe o servidor.

Os pesos ficam fora do pacote, em `models/`, baixados uma única vez com revisão fixa —
é o que o regulamento pede no pacote de verificação. Depois do download a execução é
offline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from cacador_alucinacoes.extraction import DEFAULT_MODEL
from cacador_alucinacoes.goldenset import ROOT

MODEL_REPO = "Qwen/Qwen3-8B-FP8"
# O commit que está em `models/Qwen3-8B-FP8/.cache/huggingface/download/*.metadata` —
# os pesos com que todas as medições foram feitas.
MODEL_REVISION = "220b46e3b2180893580a4454f21f22d3ebb187d3"
MODEL_DIR = ROOT / "models" / "Qwen3-8B-FP8"

PORT = 8000
HEALTH_URL = f"http://localhost:{PORT}/health"

SERVER_FLAGS = (
    f"--served-model-name={DEFAULT_MODEL}",
    # O KV cache cabe ~12 mil tokens; serializamos para ter determinismo, então o
    # orçamento inteiro vai para uma requisição e o modo de raciocínio não é truncado.
    "--max-model-len=12000",
    # 0.85 bastava no container; fora dele, na 5070 Ti de 16 GB com o desktop no ar,
    # sobraram 1,37 GiB de KV cache contra 1,65 GiB exigidos. 0.88 dá 3,9 GiB. Só
    # reserva memória — não muda a saída.
    "--gpu-memory-utilization=0.88",
    # Sem isto o vLLM adota o `generation_config.json` do Qwen3 (`do_sample: true`,
    # temperature 0.6) como default do servidor, e a saída deixa de ser reprodutível
    # mesmo com temperature=0 na requisição.
    "--generation-config=vllm",
    f"--port={PORT}",
)

# Medido: da partida ao `/health` levou ~2 min nesta máquina (compilação + CUDA graphs).
# A primeira execução compila do zero e demora mais.
STARTUP_TIMEOUT = 900


def weights_complete(directory: Path) -> bool:
    """A pasta tem o modelo inteiro, não só o começo de um download interrompido.

    Olhar só o `config.json` não basta: ele chega antes dos pesos, e um download cortado
    no meio deixaria a pasta com cara de pronta e o vLLM falhando ao carregar. Então se
    exige cada shard listado no índice, e nenhuma sobra `.incomplete` do Hugging Face.
    """
    index = directory / "model.safetensors.index.json"
    if not (directory / "config.json").exists() or not index.exists():
        return False
    shards = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
    if not all((directory / shard).exists() for shard in shards):
        return False
    return not any(directory.glob(".cache/huggingface/download/**/*.incomplete"))


def ensure_weights(directory: Path = MODEL_DIR) -> Path:
    """Baixa os pesos na revisão fixa, se não estiverem completos em disco.

    Um download interrompido é retomado de onde parou: o `snapshot_download` pula o que
    já está íntegro.
    """
    if weights_complete(directory):
        return directory
    from huggingface_hub import snapshot_download

    print(f"baixando {MODEL_REPO}@{MODEL_REVISION[:8]} para {directory} ...", flush=True)
    snapshot_download(MODEL_REPO, revision=MODEL_REVISION, local_dir=directory)
    return directory


def _healthy() -> bool:
    try:
        return httpx.get(HEALTH_URL, timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@contextmanager
def serving(model_dir: Path, log_path: Path):
    """Sobe o vLLM, espera ficar saudável e o derruba na saída.

    Se já houver um servidor respondendo na porta, ele é reaproveitado e não é derrubado
    — útil para rodar o pipeline várias vezes sem pagar a partida a cada uma.
    """
    if _healthy():
        print(f"servidor da LLM já no ar em {HEALTH_URL}; reaproveitando.", flush=True)
        yield
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    vllm = Path(sys.executable).with_name("vllm")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [str(vllm), "serve", str(model_dir), *SERVER_FLAGS],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
        )
        try:
            print(f"subindo o vLLM (log em {log_path}) ...", flush=True)
            deadline = time.monotonic() + STARTUP_TIMEOUT
            while not _healthy():
                if process.poll() is not None:
                    sys.exit(f"o vLLM terminou na partida; ver {log_path}")
                if time.monotonic() > deadline:
                    sys.exit(f"o vLLM não ficou pronto em {STARTUP_TIMEOUT}s; ver {log_path}")
                time.sleep(5)
            print("vLLM pronto.", flush=True)
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
