# 🧺 Sistema de Lavanderia – LaundryPro

Sistema web completo para programação de lavanderia industrial.

## Requisitos
- Python 3.8+

## Instalação e Execução

```bash
# 1. Instalar dependências
pip install flask flask-sqlalchemy

# 2. Entrar na pasta do projeto
cd lavanderia

# 3. Rodar o servidor
python app.py

# 4. Acessar no navegador
http://localhost:5000
```

## Funcionalidades

### 📊 Dashboard
- Visão geral de todas as máquinas
- Estatísticas de cargas, peso e status em tempo real

### 📋 Ordens de Produção (OP)
- Cadastro com OP, Referência e Tipo de Lavação
- Lançamento de quantidade por tamanho:
  - Adulto letras: PP, P, M, G, GG, XG
  - Adulto numérico: 32 a 50
  - Infantil: 01 a 16
- Peso por tamanho (kg/peça)
- Cálculo automático do Peso Total
- **Botão Arredondar Cargas**: divide o peso total pela capacidade e arredonda para cima

### 🫧 Máquinas de Lavar (10 máquinas)
- Configuração de capacidade (kg) e tempo por carga (min)
- **Geração automática em cascata**: informe OP, Referência, data e hora da 1ª carga → todas as cargas subsequentes são calculadas automaticamente
- Controle de status: Aguardando / Em Processo / Concluído
- Edição inline de cada carga

### 🌀 Centrífugas (6 máquinas)
- Mesmo sistema das lavadoras
- Capacidade padrão 80 kg, tempo padrão 15 min

### ♨️ Secadores (11 máquinas)
- Mesmo sistema das lavadoras
- Capacidade padrão 60 kg, tempo padrão 45 min

### 📅 Calendário de Turnos
- Calendário mensal navegável
- 3 turnos por dia (05h–13h, 13h–21h, 21h–05h)
- Registro de Horas Extras com cálculo automático
- Indicadores visuais no calendário

## Banco de Dados
SQLite local – arquivo `lavanderia.db` criado automaticamente na primeira execução.
