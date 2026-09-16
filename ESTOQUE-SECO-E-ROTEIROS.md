# Estoque seco e roteiros

Abra **Estoque seco e roteiros** no menu ou `/estoque-seco`.

## Uso

1. Cadastre a OP e a referência, com quantidades por tamanho e peso de uma peça
   de cada tamanho em kg. O cadastro é o mesmo utilizado nas demais telas.
2. Informe o responsável, escolha uma receita com instruções e defina o roteiro.
   As fases iniciais são exemplos: selecione, ordene, retire ou repita conforme
   o produto. É possível cadastrar fases próprias e salvar modelos reutilizáveis.
3. O roteiro começa no estoque seco e termina em **Passadoria final** ou
   **Laser final**. Uma fase intermediária com esses nomes não libera a OP.
4. Clique em **Movimentar**, escolha a máquina quando o setor usa equipamento
   e, se necessário, informe o início planejado. Sem horário, a programação
   começa após a última previsão pendente daquele equipamento.
5. Conclua cargas nas máquinas ou itens nas filas existentes de laser e
   passadoria. Em diferenciado/outros setores manuais, confirme a conclusão
   no fluxo da OP. Atualize o andamento para liberar a próxima movimentação.
6. Ao concluir todas as fases, a OP fica pronta para faturamento. A emissão
   continua sendo uma ação separada na tela de Faturamento, com preço cadastrado.

Cada transferência movimenta a quantidade integral da OP. Cargas podem terminar
separadamente, mas a próxima fase aguarda todas as cargas da passagem atual.
Essa primeira versão não implementa movimentação parcial entre setores, perdas
de peças ou faturamento automático. A conclusão de uma carga exige conferir sua
quantidade integral; divergências precisam ser esclarecidas antes de confirmar.

## Controles

- Receita e roteiro obrigatórios antes de movimentar; cada fase pode usar outra
  receita. Uma cópia das receitas e instruções é preservada na OP.
- Todos os tamanhos com peças precisam de peso positivo, com até três casas
  decimais em kg. A distribuição respeita a capacidade e preserva peças inteiras.
- Pesos, quantidades, identidade e roteiro ficam protegidos depois da primeira
  transferência. Alterar uma receita de cadastro não reescreve a OP em produção.
- Passagens repetidas têm vínculos distintos com suas cargas/filas. Retorno
  programado não cria um registro de retrabalho de qualidade.
- Movimentações e conclusões guardam responsável e horário. O nome informado
  identifica autoria declarada, conforme os apontamentos já existentes.
- Programação direta de novas OPs pelas rotas antigas é bloqueada. As telas de
  máquinas mantêm apontamentos, horários e parâmetros das cargas transferidas.
- O bloqueio de faturamento vale na interface e na API, inclusive para OPs
  sem roteiro. Finalizar apenas uma lavagem não libera a OP.

## OPs anteriores à mudança

OPs com cargas/filas, etapas iniciadas ou faturamento anterior aparecem como
produção anterior, sem presumir que voltaram ao estoque seco. Para adotar o novo
fluxo, conclua as filas anteriores, cadastre o roteiro e confirme explicitamente
quantas fases já terminaram, com responsável e motivo. Estoque seco conta como
fase 1. A conferência preserva o histórico e não inventa datas reais anteriores.
Não é permitido reabrir como saldo seco uma OP já identificada como produzida.

O saldo seco exibido corresponde às OPs ainda não transferidas. Recebimentos
adicionais, devoluções, perdas e ajustes parciais não fazem parte desta etapa.
O controle do tratamento de água permanece como próxima etapa solicitada.

## Validação

`python -m unittest test_fluxo test_inicializacao test_operacao test_gestao test_relatorios`
usa banco isolado. `node test_browser_fluxo.cjs` usa `test_browser_server.py`
na porta 5001 para testar o fluxo nas telas e a integração com as filas.
Os testes de navegador existentes de operação, gestão e programação foram
adaptados à movimentação obrigatória por roteiro.

As tabelas novas são criadas pela inicialização WSGI já existente, sem remover
tabelas ou registros antigos. A conferência de saldo histórico é uma ação
explícita do usuário, não uma migração automática dos dados de produção.
