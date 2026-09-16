# Chrona Lavanderia — conferência da versão local

As duas etapas de melhorias estão implementadas localmente. A publicação será feita depois da conferência com o usuário.

## Abrir

Execute `Abrir Chrona Lavanderia.bat` e acesse http://127.0.0.1:5000. Se uma versão anterior estiver aberta, encerre-a com Ctrl+C antes de iniciar novamente. Atualize a página com Ctrl+F5.

O banco local é separado do sistema hospedado. Os testes automatizados utilizam outro banco, em memória, e não inserem seus exemplos no banco local.

## Sequência para conferir

**Relatórios:** em Visão geral → Relatórios, confira produção por máquina, acompanhamento de OPs e custos por OP. Teste período, busca, seleção de máquina, exportação CSV e impressão/PDF. Para OPs e custos, informe previamente um prazo de entrega na ficha dentro do período escolhido. Ao mudar um filtro, clique em Gerar relatório antes de imprimir.

1. **Dashboard e modo operador:** confira o dia da produção, os kg previstos e realizados por etapa e os alertas. Em uma carga de teste, informe o operador, inicie, pause com motivo, retome e conclua. Confira o histórico.
2. **Ordens de Produção:** cadastre uma OP de teste com quantidade e peso das peças. Cadastre os preços se desejar testar faturamento e margem.
3. **Acompanhamento de OPs:** abra a ficha, informe o responsável pelo registro, cliente, responsável pela OP, prazo e receita prevista total. Salve.
4. **Roteiro:** em Configurar roteiro e responsáveis, adicione as etapas na ordem desejada. Use a seta para reorganizar antes do início. Sem cargas vinculadas, teste qualidade e expedição, avançando uma de cada vez. Quando houver programação vinculada, confira o andamento recebido dessas cargas ou filas.
5. **Custos:** lance um custo previsto, depois seu realizado. Teste a importação de químicos de uma receita e o uso do CPM de funcionário para mão de obra. A importação não retira produtos do estoque.
6. **Margem:** confira receita prevista menos custo previsto. Após faturar a OP e preencher os custos realizados, confira faturamento menos custo realizado. Faturamento parcial produz margem parcial.
7. **Arquivados:** use Arquivar em um cadastro de teste, informe nome e motivo, confira que saiu da lista, abra Arquivados e consulte o histórico. Restaure e confira seu retorno.
8. **Celular:** confira o menu, a ficha da OP, os formulários e os botões do modo operador.

## Antes da publicação

Após a aprovação das telas e regras, preparar backup do banco hospedado, validar a criação das novas tabelas em cópia PostgreSQL dos dados reais e executar os cenários principais nessa cópia. Em seguida, publicar a versão aprovada e conferir os fluxos essenciais no ambiente hospedado.

O nome informado nos apontamentos identifica a autoria declarada; o sistema ainda não possui autenticação individual. Não houve alteração de credenciais ou publicação durante esta etapa.
