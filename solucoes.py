# -*- coding: utf-8 -*-
"""Registro de soluções do desafio Caça-Alucinações.

Cada solução é uma função `fn(texto, doc_id, ctx) -> list[citacao]`, onde cada
citacao é um dict no formato do contrato (inicio, fim, trecho, tipo,
classificacao, resolucao). `ctx` carrega o Resolvedor (consulta ao .db).
"""

REGISTRO = []
