from __future__ import annotations

import re
from typing import Any

from challenge_jusbrasil.busca.base import contexto_de, gravar
from challenge_jusbrasil.resolver import Resolver
from challenge_jusbrasil.resolver.comum import Resolucao
from challenge_jusbrasil.resolver.lei import diploma_do_trecho, tipo_de
from challenge_jusbrasil.settings import (
    GLINER_LIMIAR,
    GLINER_LIMIAR_PROCESSO,
    GLINER_MODEL,
)

_TRIBUNAIS = {"STF", "STJ", "TST", "TSE", "STM"}
_DIGITO = re.compile(r"\d")
_PROCESSO = re.compile(r"\d[\d.\-/]{2,}")
_CAMPOS = ("artigo", "sumula", "processo")


def _como_dict(resultado: Any) -> dict[str, Any]:
    if hasattr(resultado, "to_dict"):
        resultado = resultado.to_dict()
    return resultado if isinstance(resultado, dict) else {}


def _confianca(valor: Any) -> float | None:
    if isinstance(valor, dict) and "confidence" in valor:
        try:
            return float(valor["confidence"])
        except (TypeError, ValueError):
            return None
    return None


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        texto = valor.strip()
        return texto or None
    if isinstance(valor, dict):
        if "text" in valor:
            return _texto(valor.get("text"))
        if "label" in valor:
            return _texto(valor.get("label"))
        return None
    if isinstance(valor, (list, tuple)):
        for item in valor:
            achado = _texto(item)
            if achado:
                return achado
    return None


def _primeiro(valor: Any) -> Any:
    if isinstance(valor, list):
        return valor[0] if valor else None
    return valor


def _achatar(resultado: Any) -> dict[str, Any]:
    bruto = _como_dict(resultado)
    registro: dict[str, Any] = {}
    citacao = _primeiro(bruto.get("citacao"))
    if isinstance(citacao, dict):
        registro.update(citacao)
    entidades = bruto.get("entities")
    if not isinstance(entidades, dict):
        return registro
    for chave, valor in entidades.items():
        item = _primeiro(valor)
        if _texto(registro.get(chave)) is None:
            registro[chave] = item
        if isinstance(item, dict):
            for atributo in ("tribunal", "vinculante"):
                if atributo in item and registro.get(atributo) is None:
                    registro[atributo] = item[atributo]
    return registro


def _aceito(valor: Any, padrao: re.Pattern[str], limiar: float) -> str | None:
    confianca = _confianca(valor)
    if confianca is not None and confianca < limiar:
        return None
    texto = _texto(valor)
    if texto is None or padrao.search(texto) is None:
        return None
    return texto


def _tribunal(registro: dict[str, Any]) -> str | None:
    texto = _texto(registro.get("tribunal"))
    if texto is None:
        return None
    sigla = texto.upper()
    return sigla if sigla in _TRIBUNAIS else None


def _vinculante(registro: dict[str, Any], trecho: str) -> bool:
    bruto = registro.get("vinculante")
    if isinstance(bruto, dict):
        return str(bruto.get("label") or "").strip().lower() == "sim"
    texto = _texto(bruto)
    if texto is not None:
        return texto.lower() in {"sim", "true", "vinculante"}
    return "vinculante" in trecho.lower()


class BuscaGliner:
    nome = "gliner"

    def __init__(self, resolver: Resolver) -> None:
        from gliner2 import AttributeGroup, AutoExtractor, RegexValidator

        print(f"load {GLINER_MODEL}", flush=True)
        self.resolver = resolver
        self.modelo = AutoExtractor.from_pretrained(GLINER_MODEL)
        self.schema = (
            self.modelo.create_schema()
            .entities(
                {
                    "artigo": "número do artigo de lei, como 373 em art. 373 do CPC",
                    "sumula": "número da súmula, como 10 em Súmula Vinculante 10",
                    "processo": "número do processo ou do acórdão, como 1.599.910 em REsp 1.599.910/PR",
                }
            )
            .entity_attributes(
                {
                    "vinculante": AttributeGroup(
                        ["sim", "nao"],
                        applies_to=["sumula"],
                    ),
                    "tribunal": AttributeGroup(
                        list(_TRIBUNAIS),
                        applies_to=["sumula", "processo"],
                    ),
                }
            )
            .structure("citacao")
            .field(
                "artigo",
                dtype="str",
                threshold=GLINER_LIMIAR,
                validators=[RegexValidator(r"\d", mode="partial")],
            )
            .field(
                "sumula",
                dtype="str",
                threshold=GLINER_LIMIAR,
                validators=[RegexValidator(r"\d", mode="partial")],
            )
            .field(
                "processo",
                dtype="str",
                threshold=GLINER_LIMIAR_PROCESSO,
                validators=[RegexValidator(r"\d[\d.\-/]{2,}", mode="partial")],
            )
            .field("tribunal", dtype="str", choices=sorted(_TRIBUNAIS))
        )

    def aplicar(self, texto: str, citacoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for cit in citacoes:
            trecho = str(cit["trecho"])
            bruto = self.modelo.extract(
                trecho,
                self.schema,
                include_spans=True,
                include_confidence=True,
            )
            tipo, resultado = self._resolver(trecho, contexto_de(texto, cit), _achatar(bruto))
            gravar(cit, tipo, resultado)
        return citacoes

    def _resolver(
        self,
        trecho: str,
        contexto: str,
        registro: dict[str, Any],
    ) -> tuple[str, Resolucao]:
        artigo = _aceito(registro.get("artigo"), _DIGITO, GLINER_LIMIAR)
        sumula = _aceito(registro.get("sumula"), _DIGITO, GLINER_LIMIAR)
        processo = _aceito(registro.get("processo"), _PROCESSO, GLINER_LIMIAR_PROCESSO)
        candidatos: list[tuple[float, int, str]] = []
        if sumula is not None:
            candidatos.append((_confianca(registro.get("sumula")) or GLINER_LIMIAR, 3, "sumula"))
        if artigo is not None:
            candidatos.append((_confianca(registro.get("artigo")) or GLINER_LIMIAR, 2, "artigo"))
        if processo is not None:
            candidatos.append((_confianca(registro.get("processo")) or GLINER_LIMIAR_PROCESSO, 1, "processo"))
        if not candidatos:
            return tipo_de(trecho), Resolucao("incompleta")
        _, _, escolhido = max(candidatos)
        if escolhido == "sumula" and sumula is not None:
            return "jurisprudencia", self.resolver.sumula.resolve_campos(
                sumula,
                _vinculante(registro, trecho),
                _tribunal(registro),
            )
        if escolhido == "artigo" and artigo is not None:
            diploma = diploma_do_trecho(artigo) or diploma_do_trecho(trecho)
            return "lei", self.resolver.lei.resolve_campos(artigo, diploma)
        if processo is not None:
            return "jurisprudencia", self.resolver.acordao.resolve(processo, contexto)
        return tipo_de(trecho), Resolucao("incompleta")
