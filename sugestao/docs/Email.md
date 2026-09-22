
Desafio BRACIS <desafio-bracis@jusbrasil.com.br>
sex., 28 de ago., 18:50 (há 22 horas)
para Cco:mim

Olá, pessoal!

Respostas às dúvidas recentes e três atualizações no dataset, válidas para todas as equipes.

1) MÉTRICAS E PLATAFORMA DE SUBMISSÃO

Até terça (01/09) vocês recebem a plataforma, o script de avaliação e os detalhes da métrica. O script é o mesmo da avaliação oficial: todo score é reproduzível localmente.

2) FORMATO DE SAÍDA

Não existe validador separado, as checagens de formato são feitas pelo próprio script de avaliação. O fluxo: um JSON por documento processado (formato do Contrato de Entrada e Saída); o conversor json_to_submission.py agrupa tudo no submission.csv. Na entrega final, o JSON completo é obrigatório, com todos os campos (trecho e tipo inclusive).

3) DATASET: TRÊS ATUALIZAÇÕES

1. Documento corrigido. O gen_n2_010.txt (nível 2) foi ajustado. Os offsets do goldenset já refletem o texto novo.
2. Base canônica atualizada. Removemos dois acórdãos do desafio1_bracis.db: doc_0227 e doc_0461. Os dois eram duplicatas exatas, o mesmo julgado indexado duas vezes, com texto idêntico sob doc_ids diferentes. Isso criava duas respostas certas para a mesma citação.

O banco passou de 1.018 para 1.016 registros (998 acórdãos, 13 dispositivos de lei, 5 súmulas).

Existem outras duplicatas no acervo, mas elas não têm par no goldenset, nenhuma citação aponta para elas, então não afetam a avaliação.

3. Mudança no contrato de saída: id_canonico passa a ser um único doc_id.

Antes o campo era um conjunto de candidatos, justamente para acomodar essas duplicatas. Com elas fora da base, cada citação real resolve para exatamente um registro. O goldenset já está assim, as 96 citações real têm um id cada.

4) AMBIENTE DE EXECUÇÃO, REGRAS DE MODELO E EXECUÇÃO

Modelo permitido: só pesos abertos, públicos e executáveis por vocês, declarados por link HF + revisão fixa. Nada de API paga/fechada.

Envelope de execução: 1 GPU 24 GB, 8 vCPUs, 32 GB RAM; média ≤ 60 s/documento; teto de 4 h no teste completo.

Execução offline: o container roda sem rede; a base de referência é fornecida por vocês e os pesos são obtidos da revisão HF declarada. Deixe explícito que não pode depender de nenhuma chamada externa em runtime.

Casos de borda: fine-tune exige publicar os pesos resultantes (HF + revisão); modelo gated só se vocês conseguem acesso gratuito, e ele deve sinalizar.

5) SUBMISSÃO E REPRODUTIBILIDADE

Submissão ao leaderboard: .zip de saídas (leve).

Pacote de verificação: repo + Dockerfile (ambiente, deps pinadas) + entrypoint no contrato padrão + manifesto do modelo (HF id + revisão) + README + seed/decodificação determinística. Pesos e dados não vão dentro da imagem.

Contrato de execução fixo, com Dockerfile + entrypoint de exemplo no kit (ex.: docker run  --input /data/in --output /data/out).

Processo de verificação e critério: re-execução das top-N + amostra; score reproduzido não pode cair mais que 5% (relativo); não rodar / não bater / violar regra de modelo = desclassifica.

 dados_desafio_jusbrasil.zip

Sigam reportando qualquer dúvida.

Abraços,

Equipe organizadora - Desafio Jusbrasil · BRACIS 2026
