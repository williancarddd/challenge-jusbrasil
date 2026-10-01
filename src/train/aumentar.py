from __future__ import annotations

import csv
import json
import random
import re
import zlib
from pathlib import Path

from challenge_jusbrasil.settings import GOLDENSET_PATH, ROOT, TXT_DIR

SAIDA = ROOT / "data" / "train"
SEMENTE = 42

_SINONIMOS = (
    ("Cumpre observar que", "Convém registrar que"),
    ("Cumpre destacar", "Importa sublinhar"),
    ("Cumpre lembrar", "Cabe recordar"),
    ("Vale invocar", "Cabe trazer à colação"),
    ("Antes de avançar, convém delimitar", "De início, cabe precisar"),
    ("A questão de fundo comporta solução", "O mérito admite deslinde"),
    ("O ponto nodal da discussão reside", "O cerne da controvérsia está"),
    ("A parte contrária limita-se a repisar", "A parte adversa se restringe a reiterar"),
    ("Nesse exato sentido caminha", "Na mesma direção segue"),
    ("O raciocínio desenvolvido no acórdão recorrido parte de premissa equivocada", "O acórdão recorrido assenta premissa que não se sustenta"),
    ("É o que se tinha a expor", "Era o que cumpria expor"),
    ("Decido.", "Passo a decidir."),
    ("Vieram os autos conclusos.", "Os autos retornaram conclusos."),
)

_FRASES = (
    "Os autos foram distribuídos livremente a este gabinete.",
    "Não há preliminar de nulidade a examinar de ofício.",
    "O preparo foi comprovado nos autos.",
    "A intimação da parte contrária observou o prazo legal.",
    "O exame se limita ao que foi devolvido no recurso.",
)

_NOMES = (
    "HELENA DUARTE PIMENTEL",
    "OFICINA LITORAL LTDA.",
    "COOPERATIVA VALE VERDE",
    "MARINA COSTA ALBUQUERQUE",
    "METALÚRGICA SERRA DOURADA S.A.",
    "PAULO HENRIQUE VASCONCELOS",
)

_CIDADES = ("Recife", "Curitiba", "Belém", "Florianópolis", "Campo Grande")
_PROCESSO = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
_FLS = re.compile(r"fls\.\s*\d+/\d+", re.IGNORECASE)
_VALOR = re.compile(r"R\$\s*[\d.]+,\d{2}")
_DATA = re.compile(r"\d{1,2} de [a-zç]+ de \d{4}", re.IGNORECASE)


def spans_do_gabarito(doc_id: str, goldenset_path: Path = GOLDENSET_PATH) -> list[tuple[int, int]]:
    spans = []
    with goldenset_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["documento_id"] == doc_id:
                spans.append((int(row["inicio"]), int(row["fim"])))
    spans.sort()
    return spans


def segmentos(texto: str, spans: list[tuple[int, int]]) -> list[tuple[str, str]]:
    partes: list[tuple[str, str]] = []
    cursor = 0
    for inicio, fim in spans:
        partes.append(("livre", texto[cursor:inicio]))
        partes.append(("fixo", texto[inicio:fim]))
        cursor = fim
    partes.append(("livre", texto[cursor:]))
    return partes


def juntar(partes: list[tuple[str, str]]) -> str:
    return "".join(trecho for _, trecho in partes)


def mapear_livre(partes: list[tuple[str, str]], func) -> list[tuple[str, str]]:
    return [(tipo, func(trecho) if tipo == "livre" else trecho) for tipo, trecho in partes]


def _sinonimos(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    pares = list(_SINONIMOS)
    rng.shuffle(pares)

    def aplicar(trecho: str) -> str:
        for origem, destino in pares:
            trecho = trecho.replace(origem, destino)
        return trecho

    return mapear_livre(partes, aplicar)


def _ocr(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    trocas = {"a": "ã", "e": "c", "o": "e", "i": "l", "u": "n", "m": "rn"}

    def aplicar(trecho: str) -> str:
        chars = []
        for char in trecho:
            if char.lower() in trocas and rng.random() < 0.04 and char.isalpha():
                novo = trocas[char.lower()]
                chars.append(novo.upper() if char.isupper() else novo)
            else:
                chars.append(char)
        return "".join(chars)

    return mapear_livre(partes, aplicar)


def _insere(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    frase = rng.choice(_FRASES)
    livres = [indice for indice, (tipo, trecho) in enumerate(partes) if tipo == "livre" and len(trecho) > 80]
    if not livres:
        return partes
    indice = rng.choice(livres)
    tipo, trecho = partes[indice]
    partes = partes[:]
    partes[indice] = (tipo, trecho.rstrip() + " " + frase + "\n")
    return partes


def _remove_frase(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    def aplicar(trecho: str) -> str:
        frases = re.split(r"(?<=[.!?])\s+", trecho)
        candidatas = [indice for indice, frase in enumerate(frases) if 40 < len(frase) < 180]
        if not candidatas:
            return trecho
        del frases[rng.choice(candidatas)]
        return " ".join(frases)

    return mapear_livre(partes, aplicar)


def _troca_nomes(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    texto = juntar(partes)
    achados = re.findall(r"(?m)^(?:[\wÀ-ú/ .()-]{0,40}:\s*)([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ./-]{8,})$", texto)
    achados = [nome.strip() for nome in achados if len(nome.strip()) > 8]
    if not achados:
        return partes
    substitutos = rng.sample(_NOMES, k=min(len(_NOMES), len(achados)))

    def aplicar(trecho: str) -> str:
        for nome, novo in zip(achados, substitutos):
            trecho = trecho.replace(nome, novo)
        return trecho

    return mapear_livre(partes, aplicar)


def _troca_protocolo(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    def processo() -> str:
        return (
            f"{rng.randint(1000000, 9999999)}-{rng.randint(10, 99)}."
            f"{rng.randint(2018, 2024)}.{rng.randint(1, 8)}.{rng.randint(1, 27):02d}.{rng.randint(1, 9999):04d}"
        )

    def aplicar(trecho: str) -> str:
        trecho = _PROCESSO.sub(processo(), trecho)
        trecho = _FLS.sub(lambda _: f"fls. {rng.randint(100, 900)}/{rng.randint(100, 980)}", trecho)
        trecho = _VALOR.sub(lambda _: f"R$ {rng.randint(1, 80)}.000,00", trecho)
        return trecho

    return mapear_livre(partes, aplicar)


def _reordena(texto: str, spans: list[tuple[int, int]], rng: random.Random) -> str:
    blocos = texto.split("\n\n")
    inicios = []
    pos = 0
    for indice, bloco in enumerate(blocos):
        inicios.append(pos)
        pos += len(bloco) + (2 if indice < len(blocos) - 1 else 0)
    livres = []
    for indice, bloco in enumerate(blocos):
        começo = inicios[indice]
        fim = começo + len(bloco)
        if not any(inicio < fim and termino > começo for inicio, termino in spans):
            livres.append(indice)
    if len(livres) < 2:
        return texto
    ordem = livres[:]
    rng.shuffle(ordem)
    novos = blocos[:]
    for destino, origem in zip(livres, ordem):
        novos[destino] = blocos[origem]
    return "\n\n".join(novos)


def _troca_data(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    cidade = rng.choice(_CIDADES)
    meses = ("janeiro", "março", "maio", "agosto", "outubro")

    def aplicar(trecho: str) -> str:
        for nome in ("Fortaleza", "São Paulo", "Brasília", "Rio de Janeiro", "Belo Horizonte", "Porto Alegre"):
            trecho = trecho.replace(nome, cidade)
        trecho = _DATA.sub(
            lambda _: f"{rng.randint(1, 28)} de {rng.choice(meses)} de {rng.randint(2020, 2025)}",
            trecho,
        )
        return trecho

    return mapear_livre(partes, aplicar)


def _expande(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    paragrafo = (
        "\n\nNada mais havendo a considerar no âmbito deste exame, "
        "encaminhem-se os autos ao arquivo próprio após as anotações de praxe, "
        f"com ciência às partes pelo meio ordinário. ({rng.choice(_CIDADES)}.)\n"
    )
    if not partes:
        return partes
    tipo, trecho = partes[-1]
    partes = partes[:]
    partes[-1] = (tipo, trecho + paragrafo)
    return partes


def _combina(partes: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    return _troca_protocolo(_insere(_sinonimos(partes, rng), rng), rng)


_OPERACOES = (
    "sinonimos",
    "ocr",
    "insere",
    "remove_frase",
    "troca_nomes",
    "troca_protocolo",
    "reordena",
    "troca_data",
    "expande",
    "combina",
)


def aumentar_texto(texto: str, spans: list[tuple[int, int]], operacao: str, rng: random.Random) -> str:
    if operacao == "reordena":
        return _reordena(texto, spans, rng)
    partes = segmentos(texto, spans)
    funcoes = {
        "sinonimos": _sinonimos,
        "ocr": _ocr,
        "insere": _insere,
        "remove_frase": _remove_frase,
        "troca_nomes": _troca_nomes,
        "troca_protocolo": _troca_protocolo,
        "troca_data": _troca_data,
        "expande": _expande,
        "combina": _combina,
    }
    return juntar(funcoes[operacao](partes, rng))


def gerar(txt_dir: Path = TXT_DIR, saida: Path = SAIDA, semente: int = SEMENTE) -> Path:
    rng = random.Random(semente)
    fontes = rng.sample(sorted(txt_dir.glob("*.txt")), 5)
    saida.mkdir(parents=True, exist_ok=True)
    manifesto = saida / "manifest.jsonl"
    linhas = []
    for fonte in fontes:
        texto = fonte.read_text(encoding="utf-8")
        spans = spans_do_gabarito(fonte.stem)
        for indice, operacao in enumerate(_OPERACOES, start=1):
            variante = aumentar_texto(
                texto,
                spans,
                operacao,
                random.Random(semente + indice * 1009 + zlib.adler32(fonte.stem.encode()) % 10000),
            )
            for inicio, fim in spans:
                original = texto[inicio:fim]
                if original not in variante:
                    raise SystemExit(f"citação perdida em {fonte.stem} {operacao}")
            nome = f"{fonte.stem}_aug{indice:02d}.txt"
            (saida / nome).write_text(variante, encoding="utf-8")
            linhas.append(
                {
                    "arquivo": nome,
                    "origem": fonte.name,
                    "operacao": operacao,
                }
            )
    with manifesto.open("w", encoding="utf-8") as handle:
        for linha in linhas:
            handle.write(json.dumps(linha, ensure_ascii=False) + "\n")
    print(f"fontes={[fonte.name for fonte in fontes]} arquivos={len(linhas)} pasta={saida}", flush=True)
    return manifesto


if __name__ == "__main__":
    gerar()
