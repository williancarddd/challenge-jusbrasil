# -*- coding: utf-8 -*-
"""Normalização de identificadores e texto ruidoso (nível 2)."""
import difflib
import re
import unicodedata

_DATE_RE = re.compile(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\b")


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


_OCR_DIGIT_MAP = str.maketrans({
    "O": "0", "o": "0",
    "l": "1", "I": "1", "i": "1",
    "S": "5",
    "g": "9", "G": "9",
    "B": "8",
})


def only_digits(s: str) -> str:
    """Extrai só os dígitos de um trecho — cobre pontuação, espaços e quebras
    de linha no meio do número, além da confusão de OCR letra-por-dígito
    (0↔O, 1↔l/I, 5↔S) garantida pelo desafio: um dígito nunca vira outro
    dígito, só a formatação/OCR pode disfarçar um dígito de letra parecida."""
    s = s.translate(_OCR_DIGIT_MAP)
    return re.sub(r"\D", "", s)


def strip_dates(s: str) -> str:
    """Remove datas DD/MM/AAAA do texto antes de procurar o número do processo
    — evita que uma data no cabeçalho seja confundida com o número."""
    return _DATE_RE.sub(" ", s)


_OCR_LETTER = r"(?<![OolISgBG])[OolISgBG](?![OolISgBG])"  # nunca 2 seguidas (não é "III")
# espaço/tab sempre tolerados; quebra de linha só se NÃO for troca de parágrafo
# (uma citação nunca atravessa uma linha em branco para o texto seguinte)
_FILLER = r"[\d.\-]|[ \t]|\n(?!\s*\n)"
NUM_TOKEN_RE = re.compile(
    r"\d(?:" + _FILLER + "|" + _OCR_LETTER + r")*(?:\d|" + _OCR_LETTER + r")(?![A-Za-z])"
)


def extract_number_token(s: str):
    """Acha o primeiro 'token de número' num trecho livre (que pode ter texto
    ao redor, tipo 'AgInt no REsp 1.599.910/PR'): começa e termina em dígito
    (real ou letra OCR-confundível), tolera '.', '-' e um único espaço interno
    entre dígitos, e nunca engole um sufixo de UF (que começa com uma letra
    comum não-tolerada, ou some após '/', que não está na classe tolerada).
    Retorna a substring bruta encontrada (ou None)."""
    m = NUM_TOKEN_RE.search(s)
    return m.group(0) if m else None


def regroup_digits(digits: str) -> str:
    """Reagrupa uma sequência pura de dígitos de 3 em 3 a partir da direita,
    reproduzindo a forma '1.741.784' a partir de '1741784' — necessário para
    buscas por frase no FTS (unicode61 tokeniza em cada não-alfanumérico)."""
    if len(digits) <= 3:
        return digits
    parts = []
    i = len(digits)
    while i > 3:
        parts.append(digits[i - 3:i])
        i -= 3
    parts.append(digits[:i])
    parts.reverse()
    return ".".join(parts)


_UF_SET = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


def find_uf(s: str):
    m = re.search(r"\b([A-Z]{2})\b", s.upper())
    if m and m.group(1) in _UF_SET:
        return m.group(1)
    return None


# ---------------------------------------------------------------- códigos de lei

_CODIGO_ALIASES = {
    "cpc": "CPC",
    "codigo de processo civil": "CPC",
    "novo cpc": "CPC",
    "clt": "CLT",
    "consolidacao das leis do trabalho": "CLT",
    "cf": "CF",
    "cf88": "CF",
    "cf/88": "CF",
    "constituicao federal": "CF",
    "constituicao da republica": "CF",
    "cc": "CC",
    "codigo civil": "CC",
    "cpp": "CPP",
    "codigo de processo penal": "CPP",
    "cpm": "CPM",
    "codigo penal militar": "CPM",
    "cdc": "CDC",
    "codigo de defesa do consumidor": "CDC",
    "codigo eleitoral": "CE",
    "lc 64/1990": "LC64",
    "lc 64/90": "LC64",
    "lei complementar 64/1990": "LC64",
    "lei complementar no 64/1990": "LC64",
    "lei complementar 64": "LC64",
    # referência ao código pela lei que o instituiu, em vez da sigla
    "13105/2015": "CPC",
    "5452/1943": "CLT",
    "10406/2002": "CC",
    "3689/1941": "CPP",
    "1001/1969": "CPM",
    "8078/1990": "CDC",
    "4737/1965": "CE",
    "64/1990": "LC64",
}


def norm_codigo(s: str):
    """Mapeia variantes de nome de código de lei para uma chave canônica —
    inclusive quando a lei é citada pelo número/ano de promulgação em vez da
    sigla (ex.: "Lei nº 13.105/2015" em vez de "CPC")."""
    m = re.search(r"lei\s*(?:complementar\s*)?n?[º°.]?\s*([\d.]+)\s*/\s*(\d{2,4})", s,
                  flags=re.IGNORECASE)
    if m:
        numero = only_digits(m.group(1))
        ano = m.group(2)
        key = f"{numero}/{ano if len(ano) == 4 else '19' + ano}"
        if key in _CODIGO_ALIASES:
            return _CODIGO_ALIASES[key]
    key = strip_accents(s).lower()
    key = re.sub(r"[ºª°.,]", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    if key in _CODIGO_ALIASES:
        return _CODIGO_ALIASES[key]
    if key.startswith("constituicao"):
        return "CF"
    for alias, canon in _CODIGO_ALIASES.items():
        if alias in key:
            return canon
    return None


# ---------------------------------------------------------------- correção leve de OCR

_VOCAB = [
    "julgado", "acordao", "precedente", "precedentes", "proferido", "relatoria",
    "relator", "reclamacao", "sumula", "sumulado", "sumular", "verbete",
    "entendimento", "jurisprudencia", "pacifica", "consolidada", "dispositivo",
    "constitucional", "legal", "regencia", "invocado", "origem", "legislacao",
    "normas", "materia", "artigo", "correspondente", "codigo", "disciplina",
    "prescricao", "orientacao", "jurisprudencial", "corte", "superior",
    "recurso", "repetitivo", "firmado", "sede", "recente", "turma", "segunda",
    "primeira", "terceira", "quarta", "casa", "desta", "situacoes", "analogas",
    "reiterados", "stf", "stj", "tst", "tse", "stm",
]


def fuzzy_fix_word(word: str) -> str:
    """Corrige uma palavra ruidosa (OCR) contra o vocabulário de domínio,
    palavra a palavra — não tenta adivinhar caractere a caractere, então
    generaliza a erros de digitação não vistos no dev set."""
    key = strip_accents(word).lower()
    if key in _VOCAB:
        return key
    match = difflib.get_close_matches(key, _VOCAB, n=1, cutoff=0.78)
    return match[0] if match else key


def fuzzy_normalize_text(text: str) -> str:
    """Aplica fuzzy_fix_word a cada palavra alfabética do texto, preservando
    posições aproximadas — usado só para *detecção* de frases-molde vagas,
    nunca para decidir offsets (offsets sempre vêm do texto original)."""
    def repl(m):
        return fuzzy_fix_word(m.group(0))
    return re.sub(r"[A-Za-zÀ-ÿ]+", repl, text)
