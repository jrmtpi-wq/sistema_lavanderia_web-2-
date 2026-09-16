# Atualização de 16/09/2026

Inclui painel operacional, apontamentos de cargas com operador, peso e peças,
gestão e custos por OP, relatórios, impressão e telas compactas.

Corrigida a interação entre abertura do menu ao passar o mouse e clique.
O inicializador de publicação respeita PORT e desativa o depurador Flask.

Validação local em SQLite isolado:

- 25 testes de operação, gestão e relatórios aprovados.
- Navegador: ciclo do operador, cancelamento e conclusão pela programação aprovados.
- Navegador: layout global, programação de OPs, gestão, relatórios e impressão aprovados.

Os bancos locais, dependências de navegador e resultados de testes não fazem
parte da publicação. O banco hospedado continua sendo definido por DATABASE_URL.
As novas tabelas são criadas por init_db(), sem preencher datas ou medições
históricas. A validação com cópia PostgreSQL e o backup do banco hospedado não
foram realizados nesta sessão, pois não há acesso ao banco remoto.

O resultado da implantação no Render deve ser confirmado separadamente do envio
ao GitHub.
