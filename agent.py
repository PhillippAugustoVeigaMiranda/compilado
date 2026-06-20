"""
=============================================================================
AI News Agent - Compilado
=============================================================================
Agente que alimenta o site de notícias para desenvolvedores automaticamente.

FOCO DO SITE:
  - Ferramentas de IA para desenvolvimento (Copilot, Cursor, Claude, etc.)
  - Novos modelos de linguagem e o que mudam para devs
  - Frameworks, linguagens e releases relevantes
  - Mercado de trabalho em tech

FLUXO GERAL:
  1. Busca artigos de feeds RSS especializados em dev + IA
  2. Filtra os relevantes por palavras-chave técnicas
  3. Chama o Claude Haiku (Anthropic) para resumir em português e categorizar
  4. Salva em news_data.json que o site lê

COMO RODAR:
    python agent.py

VARIÁVEL DE AMBIENTE NECESSÁRIA:
    ANTHROPIC_API_KEY = sua chave da API da Anthropic
    (crie em https://console.anthropic.com/)

INSTALAÇÃO:
    pip install anthropic feedparser
=============================================================================
"""

import os
import json
import hashlib
import subprocess
import feedparser
import anthropic
from datetime import datetime, timezone
from pathlib import Path


# ── Configurações ─────────────────────────────────────────────────────────────

OUTPUT_FILE = Path(__file__).parent / "news_data.json"

# Máximo de artigos mantidos no JSON (os mais antigos são descartados)
MAX_ARTICLES_TOTAL = 30

# Limite de artigos processados por execução (controla gasto de API)
MAX_NEW_PER_RUN = 10

# Tema usado no prompt enviado ao Claude
SITE_TOPIC = "ferramentas de IA para desenvolvedores e ecossistema de desenvolvimento de software"

# ── Feeds RSS especializados em dev + IA ──────────────────────────────────────
RSS_FEEDS = [
    # Hacker News — comunidade dev, primeiros a falar de novas ferramentas
    "https://hnrss.org/frontpage",

    # Simon Willison — especialista em IA/LLMs para devs, referência no assunto
    "https://simonwillison.net/atom/everything/",

    # The Pragmatic Engineer — mercado de tech e engenharia de software
    "https://newsletter.pragmaticengineer.com/feed",

    # Dev.to — artigos escritos por devs para devs
    "https://dev.to/feed",

    # GitHub Blog — releases, novas features, Copilot, etc.
    "https://github.blog/feed/",

    # OpenAI Blog — novos modelos e APIs
    "https://openai.com/news/rss.xml",

    # The Verge Tech — cobertura ampla de tecnologia
    "https://www.theverge.com/rss/index.xml",

    # TechCrunch AI — notícias de IA e startups
    "https://techcrunch.com/category/artificial-intelligence/feed/",

    # VentureBeat AI — cobertura de IA aplicada
    "https://venturebeat.com/category/ai/feed/",

    # InfoQ — arquitetura de software e tendências de engenharia
    "https://feed.infoq.com/",
]


# ── Cliente da API Anthropic ──────────────────────────────────────────────────
# Lê a chave da variável de ambiente — nunca coloque a chave no código!
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


# ── Funções auxiliares ────────────────────────────────────────────────────────

def article_id(url: str) -> str:
    """ID único de 12 chars baseado na URL — evita duplicatas entre feeds."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def load_existing() -> dict:
    """Carrega o JSON com notícias já salvas. Retorna estrutura vazia se não existir."""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"articles": [], "last_updated": None}


def save_data(data: dict):
    """Salva as notícias no JSON que o site (index.html) vai ler."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ Salvo: {OUTPUT_FILE}")


def fetch_raw_articles() -> list[dict]:
    """
    Percorre todos os feeds RSS e coleta artigos brutos.
    Pega no máximo 5 artigos por feed (os mais recentes).
    """
    raw = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                raw.append({
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    # Limita o texto a 800 chars para não gastar tokens demais na API
                    "summary": entry.get("summary", entry.get("description", ""))[:800],
                    "source": feed.feed.get("title", url),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"⚠️  Erro ao buscar {url}: {e}")
    return raw


def is_relevant(title: str, summary: str) -> bool:
    """
    Filtro rápido por palavras-chave ANTES de chamar a API.
    Evita gastar créditos em artigos claramente fora do tema.
    """
    keywords = [
        # Ferramentas de IA para dev
        "copilot", "cursor", "claude", "chatgpt", "gpt", "gemini", "codex",
        "devin", "codeium", "tabnine", "supermaven",

        # Modelos e conceitos de IA
        "llm", "ai", "artificial intelligence", "machine learning", "deep learning",
        "neural network", "transformer", "fine-tuning", "rag", "agent",
        "openai", "anthropic", "mistral", "llama", "open source model",

        # Desenvolvimento de software
        "developer", "programming", "coding", "software engineer",
        "framework", "library", "api", "sdk", "open source",
        "github", "vscode", "ide", "terminal", "cli",
        "python", "javascript", "typescript", "rust", "go",

        # Termos em português
        "desenvolvedor", "programação", "inteligência artificial",
        "ferramenta", "código", "software",
    ]
    text = (title + " " + summary).lower()
    return any(kw in text for kw in keywords)


def process_article(raw: dict) -> dict | None:
    """
    Envia o artigo bruto ao Claude Haiku e pede:
      - Título adaptado em português
      - Resumo jornalístico focado no que muda para devs
      - Categoria entre as 5 do site
      - Nota de relevância (1-10)
      - Tags técnicas

    Retorna None se o artigo não for relevante para o foco do site.
    """
    prompt = f"""Você é editor de um portal de notícias sobre {SITE_TOPIC}.
Seu público são desenvolvedores de software brasileiros que querem saber
como a IA está mudando as ferramentas e o mercado de trabalho deles.

Analise este artigo e responda APENAS com um JSON válido no formato abaixo.
Se o artigo NÃO for relevante para esse público, retorne null.

Artigo:
Título: {raw['title']}
Fonte: {raw['source']}
Resumo original: {raw['summary']}

Formato de resposta:
{{
  "title": "título em português, direto e técnico (máx 80 chars)",
  "summary": "resumo em português focado no que isso muda para devs (2-3 frases)",
  "category": "uma de: Ferramentas | Modelos | Releases | Mercado | Tutoriais",
  "relevance_score": número de 1 a 10,
  "tags": ["tag1", "tag2", "tag3"]
}}"""

    try:
        # Claude Haiku — mais rápido e barato, ideal para classificação de textos
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text.strip()

        # Remove bloco markdown se o Claude retornar ```json ... ```
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        parsed = json.loads(text)

        # Claude retorna null quando o artigo não é relevante para o nicho
        if parsed is None:
            return None

        # Combina metadados do RSS com o conteúdo gerado pelo Claude
        return {
            "id": article_id(raw["url"]),
            "url": raw["url"],
            "source": raw["source"],
            "published": raw["published"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            **parsed,  # title, summary, category, relevance_score, tags
        }

    except Exception as e:
        print(f"  ⚠️  Erro ao processar '{raw['title'][:50]}': {e}")
        return None


# ── Função principal ──────────────────────────────────────────────────────────

def run():
    """
    Orquestra o fluxo completo:
    carrega existentes → busca RSS → filtra → processa com IA → salva
    """
    print(f"\n🤖 Compilado Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("─" * 50)

    data = load_existing()

    # Conjunto de IDs já salvos — evita reprocessar artigos antigos
    existing_ids = {a["id"] for a in data["articles"]}

    print(f"📡 Buscando feeds RSS...")
    raw_articles = fetch_raw_articles()
    print(f"   {len(raw_articles)} artigos encontrados")

    # Filtra: remove duplicatas e artigos fora do tema, limita por execução
    new_raw = [
        r for r in raw_articles
        if article_id(r["url"]) not in existing_ids and is_relevant(r["title"], r["summary"])
    ]
    new_raw = new_raw[:MAX_NEW_PER_RUN]
    print(f"   {len(new_raw)} novos para processar\n")

    # Processa cada artigo com Claude
    processed = []
    for i, raw in enumerate(new_raw, 1):
        print(f"  [{i}/{len(new_raw)}] {raw['title'][:60]}...")
        article = process_article(raw)

        # Só publica artigos com score >= 6
        if article and article.get("relevance_score", 0) >= 6:
            processed.append(article)
            print(f"       ✓ Score {article['relevance_score']} | {article['category']}")
        else:
            print(f"       ✗ Irrelevante ou baixo score")

    # Novos artigos ficam no topo; descarta os mais antigos além do limite
    data["articles"] = (processed + data["articles"])[:MAX_ARTICLES_TOTAL]
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    data["total"] = len(data["articles"])

    save_data(data)
    print(f"\n📰 Total: {data['total']} artigos | 🆕 Adicionados: {len(processed)}")

    # Só faz o push se adicionou artigos novos — evita commits desnecessários
    if processed:
        git_push(len(processed))
    else:
        print("⏭️  Nenhum artigo novo — git push ignorado")


def git_push(n_new: int) -> None:
    """
    Faz commit e push do news_data.json atualizado para o GitHub.
    O Vercel detecta o push e atualiza o site automaticamente.
    """
    print("\n🚀 Publicando no GitHub...")
    repo_dir = Path(__file__).parent

    try:
        # Adiciona só o JSON — não toca em outros arquivos
        subprocess.run(["git", "add", "news_data.json"], cwd=repo_dir, check=True)

        msg = f"atualiza noticias: +{n_new} artigos [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"
        subprocess.run(["git", "commit", "-m", msg], cwd=repo_dir, check=True)

        subprocess.run(["git", "push"], cwd=repo_dir, check=True)

        print("✅ Site atualizado no Vercel!")
    except subprocess.CalledProcessError as e:
        # Se o push falhar (sem internet, credenciais, etc.) o JSON local ainda está salvo
        print(f"⚠️  Git push falhou: {e}")
        print("   O JSON foi salvo localmente. Rode 'git push' manualmente quando possível.")


if __name__ == "__main__":
    run()
