# TechPulse AI — Portal de Notícias com Agente de IA

Site de notícias sobre Tecnologia e IA atualizado automaticamente por um agente Python.

---

## Como funciona

```
[Feeds RSS] → [agent.py filtra + resume com Claude] → [news_data.json] → [index.html lê e exibe]
```

1. `agent.py` busca notícias de feeds RSS
2. Filtra as relevantes por palavras-chave
3. Usa Claude (claude-haiku) para resumir em português e categorizar
4. Salva tudo em `news_data.json`
5. `index.html` lê esse JSON e exibe o site

---

## Setup

### 1. Instale as dependências Python

```bash
pip install anthropic feedparser
```

### 2. Configure sua API Key da Anthropic

**Windows:**
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
```

**Mac/Linux:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

> Obtenha sua chave em: https://console.anthropic.com/

### 3. Rode o agente pela primeira vez

```bash
python agent.py
```

Isso vai gerar o arquivo `news_data.json` com as primeiras notícias.

### 4. Abra o site

Abra `index.html` em um servidor local (necessário por causa da leitura do JSON):

```bash
# Python 3
python -m http.server 8080
# Acesse: http://localhost:8080
```

---

## Agendamento automático

### Windows (Task Scheduler)

```cmd
schtasks /create /tn "TechPulseAgent" /tr "python C:\caminho\agent.py" /sc hourly /mo 4
```

Isso roda o agente a cada 4 horas.

### Mac/Linux (cron)

```bash
crontab -e
# Adicione a linha abaixo (roda a cada 4 horas):
0 */4 * * * cd /caminho/do/projeto && python agent.py
```

---

## Estrutura dos arquivos

```
/
├── agent.py          # Agente de IA que busca e processa notícias
├── index.html        # Site do portal
├── news_data.json    # Gerado automaticamente pelo agente
└── README.md         # Este arquivo
```

---

## Hospedagem (custos estimados)

| Opção | Custo | Ideal para |
|-------|-------|-----------|
| **GitHub Pages** | Gratuito | Site estático (só index.html + JSON via CDN) |
| **Vercel / Netlify** | Gratuito | Deploy automático pelo Git |
| **VPS (DigitalOcean, Hetzner)** | ~$5-7/mês | Agente rodando no servidor 24/7 |
| **AWS EC2 t3.micro** | ~$8-10/mês | Controle total + escalável |

**Recomendação:** VPS de $5/mês (ex: Hetzner CX11) + GitHub Pages para o frontend.
O agente Python fica na VPS e atualiza o JSON; o site fica no GitHub Pages.

---

## Custo da API Anthropic

O agente usa **claude-haiku** (modelo mais barato da Anthropic).

- Cada artigo processado custa ~0.01 centavo de dólar
- Rodando a cada 4h com até 10 artigos por rodada = ~60 artigos/dia
- Custo estimado: **menos de $1/mês**

---

## Personalização

**Trocar o tema:** edite `SITE_TOPIC` e `RSS_FEEDS` no topo de `agent.py`

**Mudar frequência:** altere o agendamento no cron/Task Scheduler

**Adicionar fontes:** adicione URLs de RSS em `RSS_FEEDS`
