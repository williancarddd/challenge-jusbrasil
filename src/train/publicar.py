from __future__ import annotations

import argparse
import sys
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.utils import HfHubHTTPError

IGNORAR = ["**/.git/**", "**/__pycache__/**", "**/.cache/**", "**/*.pyc"]


def publicar(pasta: Path, repo: str | None) -> str:
    pasta = pasta.expanduser().resolve()
    if not pasta.is_dir():
        raise SystemExit(f"pasta ausente: {pasta}")
    if not any(caminho.is_file() for caminho in pasta.rglob("*")):
        raise SystemExit(f"pasta sem arquivos: {pasta}")

    api = HfApi()
    try:
        usuario = api.whoami()["name"]
    except (HfHubHTTPError, OSError, KeyError) as exc:
        raise SystemExit("defina HF_TOKEN com permissão de escrita ou rode `hf auth login`") from exc

    repo_id = repo or f"{usuario}/{pasta.name}"
    api.create_repo(repo_id, private=False, exist_ok=True, repo_type="model")
    api.update_repo_settings(repo_id, private=False, repo_type="model")
    print(f"enviando {pasta} para {repo_id}", file=sys.stderr)
    api.upload_folder(
        repo_id=repo_id,
        folder_path=pasta,
        repo_type="model",
        commit_message=f"publicar pesos de {pasta.name}",
        ignore_patterns=IGNORAR,
    )
    return f"https://huggingface.co/{repo_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica uma pasta de pesos no Hugging Face")
    parser.add_argument("pasta", type=Path, help="pasta com os pesos")
    parser.add_argument("--repo", help="repositório destino, ex. usuario/nome")
    args = parser.parse_args()
    print(publicar(args.pasta, args.repo))


if __name__ == "__main__":
    main()
