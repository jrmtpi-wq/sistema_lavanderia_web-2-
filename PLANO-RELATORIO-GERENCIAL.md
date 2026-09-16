# Relatório gerencial de lavanderia — especificação para implementação

Atualização: a etapa de **estoque seco, roteiros por passagem e liberação para
faturamento** foi implementada em 16/09/2026. As anotações de definição dessa
parte abaixo são históricas; consulte `ESTOQUE-SECO-E-ROTEIROS.md` para o fluxo
implementado. O relatório gerencial completo e o tratamento de água permanecem
etapas posteriores. A referência de finalização válida é a última fase do
roteiro, sendo Passadoria final ou Laser final.

Base: necessidades enviadas pelo usuário em 16/09/2026. Este documento descreve
o relatório proposto; não representa funcionalidades já implementadas.

## Entrega ao gerente

Uma nova opção em Relatórios: **Gerencial — produção, qualidade e consumos**.
Filtros de semana, mês ou período personalizado; comparação por turno e com o
período anterior; impressão/PDF e CSV para Excel. A visão geral reúne indicadores,
metas, desvio e pendências. Detalhes permitem conferir os apontamentos de origem.

O fechamento deve registrar responsável, data, versão e observações. Correções
posteriores precisam preservar o histórico e identificar a reemissão. Nenhum
campo em branco será tratado automaticamente como zero, ausência de acidentes
ou cumprimento da meta. Resultados parciais serão identificados como parciais.

## 1. Resumo executivo de produção

- Peças finalizadas no período, meta, percentual atingido e diferença em peças.
- Turnos 1, 2 e 3, com quantidade e participação de cada turno.
- Evolução diária e comparação com período anterior de duração equivalente.
- Separação entre peças boas, retrabalho, segunda qualidade e descarte.
- Definir o ponto único de contagem: aprovação na qualidade, lavagem ou secagem.
  Nunca somar as quantidades das três etapas para obter peças únicas.
- A meta de 200.000 peças é mensal. Divisão igual entre três turnos representa
  aproximadamente 66.667 peças por turno **ao longo do mês**. Distribuição por
  turno e dias úteis deve ser configurável, considerando calendário e folgas.
- Exemplo: 25 dias produtivos resultam em 8.000 peças/dia e aproximadamente
  2.667 peças por turno diário. Isso é referência de planejamento, não produção medida.
- A meta semanal deve usar os dias/turnos planejados naquela semana; não comparar
  uma semana diretamente com a meta integral de 200.000 peças.

O sistema já registra conclusão de cargas, horário real, operador, peso e peças
por lavagem, centrifugação e secagem. Esses apontamentos serão a base da visão
operacional. Ainda não identificam peças únicas que passaram por relavagem, nem
quantidades aprovadas/rejeitadas na qualidade. A conclusão do roteiro da OP não
substitui uma medição quantitativa de qualidade.

## 2. Qualidade

| Indicador | Regra | Referência inicial enviada pelo usuário |
| --- | --- | --- |
| Retrabalho | Peças distintas encaminhadas a retrabalho / peças avaliadas na mesma base × 100 | Menor que 3% |
| Segunda qualidade | Peças reclassificadas / peças avaliadas na mesma base × 100 | Exibir separadamente |
| Descarte | Peças descartadas / peças avaliadas na mesma base × 100 | Exibir separadamente |
| Segunda qualidade + descarte | Soma das duas classificações, sem duplicidade / mesma base × 100 | Menor que 0,5% |

Confirmar a base de avaliação para que numerador e denominador se refiram ao
mesmo conjunto de peças. Diferenciar peça retrabalhada de número de passagens:
uma peça lavada três vezes não pode virar três peças novas na produção.

Registrar OP/lote, quantidade, classificação, motivo, etapa de origem, turno,
responsável e data. Motivos devem permitir ranking por quantidade de peças;
se houver múltiplos motivos, definir um principal para evitar dupla contagem.
Mostrar também ações corretivas, responsável e prazo no fechamento gerencial.

Em uma base de 200.000 peças, 6.000 representam exatamente 3% e 1.000 representam
exatamente 0,5%. Como a meta proposta é **abaixo** desses percentuais, atingir
esses limites não deve receber indicação de meta cumprida. A tolerância em peças
varia com o volume real do período.

## 3. Consumos e custos

- Químicos: valor do consumo efetivo atribuído ao período / peças da base escolhida.
  Separar consumo de compras e de estoque. Preservar valor unitário na data do
  consumo. Mostrar itens, quantidade, unidade, valor e fonte do lançamento.
- Água: volume consumido em m³ × 1.000 / peças da mesma base e período.
  Registrar leitura inicial/final de hidrômetro ou consumo medido; tratar troca
  ou reinício do medidor explicitamente. Totalizar litros e m³ além de L/peça.
- Metas: químicos definidos pelo Financeiro; R$ 1,50–3,00 é exemplo recebido,
  não um limite já aprovado. Água: faixa de referência de 40–55 L/peça,
  ajustável por processo; consumo menor exige interpretação, não reprovação automática.
- ETE: operando, com restrições ou parada, com data/turno e observações.
  Mostrar ocorrências do período e situação no fechamento, sem esconder uma
  parada antiga com o último registro de funcionamento.
- Caldeira: combustível, saldo, unidade, consumo médio e autonomia em dias.
  Autonomia estimada deve exibir sua base; se declarada pelo gerente, identificar.

Hoje há estoque e movimentações de químicos, mas a movimentação não preserva
o custo unitário histórico. Custos por OP são acumulados e não possuem competência
de consumo suficiente para representar custo químico mensal. Não reavaliar meses
anteriores pelo preço atual nem usar prazo de entrega da OP como data de consumo.
Água, ETE e autonomia da caldeira precisam de novos registros.

## 4. Estoque de cru (WIP)

### Definição do usuário — estoque seco

Em 16/09/2026, o usuário solicitou registrar a criação de um **Estoque seco**,
no qual serão cadastradas todas as OPs, com quantidade por tamanho e peso por
tamanho. Aproveitar o cadastro de OPs já existente, que já contém esses dados,
mas ainda não é apresentado como estoque seco. Nesta etapa, o pedido foi apenas
de anotação. As regras de entrada, baixa e movimentação e a relação com o WIP
abaixo ainda precisam ser definidas; as fórmulas seguintes continuam propostas.

Definição seguinte do usuário: após cadastrar as OPs no estoque seco, haverá
movimentações do estoque seco para a lavanderia. No momento da movimentação,
o sistema deverá perguntar ao usuário **para qual máquina** o material será
enviado. Apenas anotado; ainda não foram definidos movimentação parcial,
momento da baixa ou geração de cargas a partir dessa transferência.

Regra obrigatória definida pelo usuário: **não permitir movimentar uma OP do
estoque seco para a lavanderia sem os pesos por tamanho cadastrados na OP**.
O usuário informou que as máquinas já possuem tudo de que precisa; aproveitar
as funcionalidades existentes nessa etapa do fluxo. Requisito apenas anotado.

Saldo final = saldo inicial + recebimentos da costura − saídas para primeira
lavagem + ajustes identificados. Definir se a saída ocorre na entrada na máquina
ou na conclusão da primeira lavagem; a definição delimita o estoque medido.
Relavagem não deve dar nova baixa no estoque de cru.

Mostrar saldo inicial, entradas, saídas, saldo final, lotes mais antigos e dias
equivalentes de produção: saldo final / capacidade diária de referência.
O saldo final é uma posição de estoque, não uma soma de saldos diários.
Referência: até dois dias. 16.000 peças equivalem a dois dias apenas quando a
capacidade usada é 8.000 peças/dia. Recebimentos, saldo de abertura e vínculo da
primeira lavagem ainda precisam de registro específico.

## 5. Máquinas e manutenção

- Horas programadas, produzindo, em pausa e paradas, por equipamento e turno.
- Disponibilidade = tempo em operação / tempo planejado para produção × 100.
- Ranking de equipamentos e motivos de parada; lista de ocorrências relevantes.
- OEE completo = disponibilidade × desempenho × qualidade. Precisa também de
  tempo/capacidade ideal por processo e contagem de peças boas na primeira passagem.
- Enquanto faltarem esses dados, mostrar disponibilidade e OEE pendente.
  A referência acima de 85% para OEE não deve ser aplicada automaticamente à
  disponibilidade como se fossem o mesmo indicador.

Apontamentos de início, pausa, retomada e conclusão existentes ajudam a medir
intervalos. Porém, pausas registradas não equivalem a toda indisponibilidade:
faltam paradas fora de uma carga, cobertura histórica e planejamento efetivo.
Não presumir que cada máquina deveria produzir 24 horas em todos os dias.
Recortar intervalos nos limites do período/turno, descontar pausas e evitar
contar simultaneamente eventos sobrepostos da mesma máquina. Totais de várias
máquinas são horas-máquina, não horas corridas da fábrica.

Referência de OEE: https://www.oee.com/calculating-oee/

## 6. Equipe e passagem de turno

- Absenteísmo = horas de ausência / horas previstas da equipe × 100,
  com detalhamento por turno e período. Definir quais ausências entram na regra.
- Acidentes e ocorrências de EPI: quantidade, situação e descrição operacional.
- Pendências da passagem de turno e ações com responsável/prazo.
- Horas previstas, ausências e ocorrências ainda precisam de registros;
  cadastro de funcionários ou jornada mensal não comprovam presença diária.
- Ausência de lançamento de acidente significa pendente; declaração explícita
  de nenhuma ocorrência significa zero confirmado.

## Coleta e calendário

Proposta: apontamento diário por turno, consolidado automaticamente em semana/mês.
O gerente revisa pendências e acrescenta resumo executivo e plano de ação no fechamento.
Não repetir a digitação de informação que já tem origem confiável no sistema.

Horário operacional: Brasília. Para o padrão atual de 05h–13h, 13h–21h e
21h–05h, identificar a data operacional pelo início do turno. Exemplo: 02h de
sábado pertence ao turno 3 iniciado na sexta. Respeitar alterações do calendário
e apresentar a convenção de datas no relatório.

Proteger apontamentos contra gravação duplicada e atualização concorrente.
Permitir correção justificada, preservando valor anterior, responsável e horário.
Dados antigos sem data real/medição confiável continuam separados; não preencher
lacunas históricas com estimativas silenciosas.

## Validação antes de publicar

Testar limites de turnos/períodos, retrabalho sem dupla contagem, períodos sem
produção, falta de apontamentos, metas nos limites exatos, estoque inicial,
consumo/preço histórico, intervalos de paradas e exportação. Conferir banco
existente com criação apenas das novas tabelas, além de celular, impressão e PDF.

## Definições solicitadas ao usuário

### Atualização: roteiros configuráveis e finalização

**Regra corrigida pelo usuário:** a fase de encerramento do roteiro pode ser
**passadoria final ou laser final**. A OP fica pronta e liberada para faturamento
somente ao concluir a última fase do roteiro, respeitando as etapas anteriores.
Se ambas estiverem presentes, prevalece sua ordem: passadoria final → laser final
libera após laser final; laser final → passadoria final libera após passadoria
final. Concluir uma dessas fases intermediariamente não encerra a OP. Esta
definição substitui a regra anterior de passadoria final exclusiva. Liberar para
faturamento não significa faturar automaticamente. Regras para conclusão ou
faturamento parcial ainda não foram definidas. Apenas registrado, não implementado.

O usuário explicou que o produto pode retornar à lavagem após diferenciado
(por exemplo, used), com novas passagens por centrífuga e secador, e só fica
pronto ao terminar a fase final. Distinguir **passadoria preparação** de
**passadoria final** e considerar também **laser final**, conforme a regra acima.
Retorno previsto no roteiro não deve contar como retrabalho de qualidade.

Cada lavanderia deve cadastrar seus próprios roteiros e escolher as fases e
sua ordem. Disponibilizar como exemplos iniciais as fases citadas pelo usuário:

- Estoque seco.
- Lavanderia preparação.
- Lavanderia final.
- Centrífuga.
- Secador.
- Passadoria preparação.
- Diferenciado.
- Laser inicial.
- Laser meio.
- Laser final.
- Lavanderia meio.
- Passadoria final.

A lista é um catálogo inicial, não um roteiro fixo nem ordem obrigatória para
todos os produtos. Alguns passam por poucas fases, outros por todas. Permitir
passagens repetidas no mesmo setor. O usuário propôs obrigatoriedade da receita
e da programação sequencial dos setores. As regras de movimentação parcial de
uma OP ainda não foram confirmadas. Estas definições estão apenas documentadas.

As perguntas abaixo são do levantamento inicial; a explicação acima esclarece
a finalização no fluxo descrito, mas não define ainda a frequência da coleta.

1. Qual etapa define produção finalizada para a meta mensal?
2. O apontamento dos dados novos será diário por turno ou somente no fechamento?

Depois: confirmar classificação de segunda qualidade/descarte, base de qualidade,
saída do estoque de cru, calendário/metas por turno e processos usados (laser,
ozônio, químicos e pedra), sem presumir que todas as tecnologias cadastradas
representem a operação efetiva da lavanderia.
