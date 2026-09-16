# Chrona Lavanderia — cópia local

## Relatórios

No menu **Visão geral → Relatórios**, escolha produção por máquina, acompanhamento de OPs ou custos por OP. Informe o período e a busca, depois clique em **Gerar relatório**. A produção permite selecionar uma máquina. Use **Exportar CSV (Excel)** para baixar a planilha ou **Imprimir / salvar PDF** para imprimir em A4 paisagem. Alterar filtros exige gerar novamente antes de imprimir.

Na produção, o período considera saída prevista e/ou conclusão real, com totais separados por lavagem, centrifugação e secagem. O peso realizado vem do apontamento de conclusão. Nos relatórios de OPs e custos, o período filtra o prazo de entrega: OPs sem prazo e arquivadas não entram. Os custos e o faturamento são acumulados atuais dessas OPs. Custos pendentes não são considerados custos finais; a margem pode ser parcial e não representa lucro líquido.

Verificação dos relatórios: `python -m unittest test_relatorios -v` e `node test_browser_relatorios.cjs` (com `python test_browser_server.py` na porta 5001). Os testes usam banco isolado; PDF e capturas ficam em `test-results/`.

Código baixado em 10/09/2026 do repositório https://github.com/jrmtpi-wq/sistema_lavanderia_web-2-, branch main, revisão a9d9617.

## Abrir no computador

Clique duas vezes em **Abrir Chrona Lavanderia.bat** e acesse **http://127.0.0.1:5000**. Mantenha a janela aberta enquanto utiliza o sistema. Para encerrar, pressione Ctrl+C nessa janela.

O inicializador usa exclusivamente `instance/chrona_local.db`, mesmo que exista DATABASE_URL no ambiente. O banco começa sem as OPs e demais registros do sistema hospedado; esses dados não fazem parte do GitHub. Não copie credenciais para o código. Para trazer os registros reais, será necessário um backup/exportação do banco ligado ao Render.

Python e Flask já estavam instalados neste computador. Em outra máquina, instale Python e execute `python -m pip install -r requirements.txt` na pasta do projeto.

## Melhorias locais — primeira etapa

- Nome Chrona Lavanderia nas telas e impressões.
- Painel por data com kg previstos e realizados separados em lavagem, centrifugação e secagem.
- Previsto: cargas cuja saída planejada está no dia selecionado. Realizado: peso registrado no momento de concluir no modo operador. As duas medidas podem conter cargas diferentes; não são uma taxa de cumprimento da programação.
- Alertas atuais de cargas com previsão vencida, estoque baixo, manutenção vencida e ordens de serviço pendentes. O filtro de data se aplica à produção; os alertas mostram a situação atual.
- Modo operador para lavadoras, centrífugas e secadores, com botões de início, pausa, retomada e conclusão, nome do operador e motivo obrigatório de pausa.
- Histórico real separado do planejamento, prevenção de duplo clique e impedimento de iniciar outra carga na mesma máquina enquanto existe uma em processo/pausada.
- Cargas com apontamentos não podem ser excluídas nem ter o status alterado pela edição antiga.

Os apontamentos usam horário de Brasília (UTC−3). Registros antigos sem apontamento de conclusão não são tratados como produção realizada do dia. O nome informado pelo operador é um registro de autoria declarada, não substitui autenticação.

## Publicação futura

Estas alterações estão apenas nesta cópia local: não houve push ao GitHub nem implantação no Render. Uma cópia ZIP do código original está na pasta acima, em `chrona-lavanderia-original-github.zip`.

A nova tabela `apontamento_carga` é criada por `init_db()` sem alterar colunas existentes. O comando atual do Render (`python app.py`) já chama essa inicialização. Caso o deploy use Gunicorn, inicialize o esquema antes de iniciar os workers. Faça backup do banco antes de publicar alterações de esquema e valide com uma cópia dos dados reais. Testes locais usam SQLite; a implantação PostgreSQL ainda precisa de validação.

## Melhorias locais — segunda etapa (11/09/2026)

- Menu agrupado em Visão geral, Produção, Cadastros, Manutenção e Financeiro, com grupos recolhíveis.
- Acompanhamento de OPs com busca, cliente, responsável, prazo, filtro de atraso e roteiro ordenado.
- Lista de OPs e seleção de OP na calculadora da máquina indicam em verde “Programada” e em vermelho “Sem programar”, conforme a existência de cargas em máquinas de lavar. Cargas de centrifugação ou secagem não contam para esse indicador; lavagem concluída continua contando como já programada. Todas as OPs ativas continuam disponíveis na seleção. A indicação atualiza ao carregar, adicionar ou remover cargas. Vínculos antigos pelo número e referência só são considerados quando identificam uma única OP.
- Roteiro com lavagem, centrifugação, secagem, laser, passadoria, robô, qualidade e expedição. Escolha apenas as etapas necessárias. Cargas e filas vinculadas alimentam o andamento; etapas sem fontes vinculadas permitem apontamento manual na sequência do roteiro.
- Datas reais das cargas vêm do modo operador. Laser, passadoria e robô mantêm o status da programação antiga; horários planejados não são apresentados como horários reais de execução.
- Custos previstos e realizados por OP nas categorias químicos, mão de obra, água, energia e outros. Valores não realizados permanecem pendentes, em vez de virar custo zero definitivo.
- Importação de químicos da receita com quantidade de execuções, preços preservados na data da importação e validação de unidades. Não movimenta estoque e impede importação duplicada da mesma receita na OP.
- Mão de obra pode usar o CPM do funcionário, preservado no lançamento. Custos realizados são informados separadamente.
- Receita prevista informada na ficha ou obtida da tabela de preços atual. Margem sobre o faturamento disponível quando todos os custos lançados têm realizado e há faturamento. Faturamento parcial gera margem parcial; o sistema não presume que todos os custos da empresa foram lançados.
- Arquivamento e restauração de OPs, funcionários, químicos, receitas, amostras, planos de manutenção, ordens de serviço concluídas, preços e faturamentos. Exige responsável e motivo, preserva registros e histórico e retira arquivados das listas de uso. Faturamento arquivado deixa de compor os totais financeiros.
- Proteções para preservar identificação de OPs acompanhadas, cargas apontadas e produção iniciada. Gerar nova programação não pode substituir cargas com produção ou apontamentos.
- Impressão da programação inclui cargas em processo e aguardando, em seções separadas, com totais e campos de entrada real, saída real e rubrica. O relatório é preparado na própria página antes de abrir a impressão, em A4 paisagem, com suporte a várias páginas. Sem cargas elegíveis, apresenta um aviso e não abre uma impressão vazia. Validação: `node test_browser_impressao.cjs` com o servidor isolado em execução; PDFs e captura em `test-results/`.
- Novas cargas e faturamentos recebem vínculo com o cadastro da OP quando a identificação é inequívoca. Referências antigas duplicadas não são somadas arbitrariamente em mais de uma ficha.

As tabelas adicionais são criadas por `init_db()`: `cadastro_arquivo`, `historico_gestao`, `ficha_op`, `etapa_op`, `custo_op` e `importacao_receita_op`, além de `apontamento_carga` da primeira etapa. Não foi realizada migração do banco hospedado. A validação em PostgreSQL e com cópia dos dados reais permanece para a preparação da publicação.

Para conferir as telas, siga `ROTEIRO-DE-CONFERENCIA.md`.

## Verificação

`python -m unittest test_operacao test_gestao -v` testa 20 cenários usando um banco isolado em memória. `node test_browser_programacao.cjs` verifica as cores e a atualização nas duas listas com o servidor isolado em execução.

Para os testes de navegador, execute `python test_browser_server.py` e, em outro terminal, `node test_browser.cjs` seguido de `node test_browser_gestao.cjs`. Requer Playwright instalado em `.browser-tools` e Microsoft Edge. Reinicie o servidor isolado antes de repetir a sequência, pois os testes alteram apenas seus dados em memória. Capturas de tela ficam em `test-results/`.

## Ajuste dos relatórios — 12/09/2026

- Calendário próprio nos campos de início e fim, mantendo digitação da data.
- Produção inclui peças concluídas e totais de quilos e peças lavadas, sem somar centrifugação/secagem ao total de lavagem.
- Cargas antigas marcadas como concluídas sem apontamento aparecem separadamente, usando a saída programada como referência de período. Isso não comprova a data real de conclusão.
- Seleção “Concluídas sem data real — todos os períodos” permite conferir o legado inteiro, sem atribuí-lo ao intervalo escolhido; disponível também no CSV/PDF.
- No banco local, na conferência desta sessão: 97 cargas concluídas sem apontamento, 8.113,863 kg e 17.456 peças. Pela saída programada de 09 a 12/09/2026: 6.851,358 kg e 14.216 peças. Há programações futuras. Aguardando confirmação do usuário sobre quais cargas efetivamente terminaram nesse período; nenhum registro histórico foi alterado.
- Verificação: quatro testes de relatórios e testes de navegador de relatórios e calendário passaram.

## Organização das máquinas — 12/09/2026

- Cabeçalho compacto e painel em toda a área da janela para lavadoras, centrífugas e secadores.
- Configuração e calculadora na seção recolhível “Programar cargas e calcular por OP”; abre recolhida ao entrar na máquina. Campos preservados ao recolher e expandir.
- Impressão acessível no cabeçalho; totais no rodapé. Colunas e cargas rolam juntas horizontalmente; títulos fixos na rolagem vertical.
- Validados layout desktop/celular, seleção de OP e impressão. Arquivos static/maquinas-layout.css e static/maquinas-layout.js.
- Usuário autorizou avançar na confiabilidade das conclusões e priorizou esta reorganização visual. Registro obrigatório de conclusão e reconciliação histórica ainda pendentes; aguardar identificação/confirmação das cargas antigas antes de alterar datas históricas.

## Padrão compacto em todas as telas — 12/09/2026

- Menu lateral recolhido em todas as larguras; botão ☰ abre navegação, seleção de página e Escape fecham o menu.
- Cabeçalhos, cartões, filtros e espaçamentos compactos em produção, cadastros, manutenção, financeiro, acompanhamento e relatórios. Conteúdo utiliza a largura da janela.
- Painéis de edição em toda a janela, com cabeçalho e rodapé compactos e corpo rolável. Ações do operador preservam tamanho para toque.
- Calculadoras de passadoria/robô e formulário da fila de laser recolhíveis; preservar campos ao expandir/recolher. Impressão mantém estilos próprios.
- Arquivos static/layout-global.css e static/layout-global.js. Verificação de todas as páginas em 1366 e 390 pixels e painéis em tela inteira; testes de gestão, relatórios e máquinas aprovados.

## Conclusão confiável de cargas — 12/09/2026

- Concluir pelo modo operador agora exige operador, peso realizado em kg e quantidade inteira de peças. Data e hora são gravadas automaticamente no horário de Brasília.
- A programação não pode mais alterar status diretamente para concluído; ao escolher concluir, abre a mesma confirmação com os dados obrigatórios. Iniciar pela programação também registra operador e horário.
- Cada conclusão preserva o peso e a medição de peças em histórico próprio, mesmo se a programação for editada depois. Cargas antigas sem medição continuam identificadas como legado pendente.
- Alterações de status por edição comum foram bloqueadas para evitar conclusões sem rastreabilidade.
- Painel diário e relatórios exibem kg realizados, peças realizadas e conclusões sem medição separadamente.
- Arquivos: operacao.py, app.py, static/conclusao.js, static/conclusao.css e testes atualizados.
- Verificação: 24 testes unitários passaram. A conferência de layout, relatórios, calendário, programação e impressão permanece aprovada. Não foram alteradas as 97 cargas antigas sem confirmação do usuário.
