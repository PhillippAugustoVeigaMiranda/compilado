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
  5. Posta o artigo mais relevante no LinkedIn
COMO RODAR:
    python agent.py
VARIÁVEIS DE AMBIENTE NECESSÁRIAS:
    ANTHROPIC_API_KEY      = sua chave da API da Anthropic
    LINKEDIN_ACCESS_TOKEN  = token OAuth do LinkedIn (dura ~2 meses)
=============================================================================
"""
import os
import json
import hashlib
import subprocess
import feedparser
import requests
import anthropic
from datetime import datetime, timezone
from pathlib import Path

# ── Configurações ──────────────────────────────────────────────────────────────
OUTPUT_FILE = Path(__file__).parent / "news_data.json"

# Máximo de artigos mantidos no JSON (os mais antigos são descartados)
MAX_ARTICLES_TOTAL = 30

# Limite de artigos processados por execução (controla gasto de API)
MAX_NEW_PER_RUN = 10

# Tema usado no prompt enviado ao Claude
SITE_TOPIC = "ferramentas de IA para desenvolvedores e ecossistema de desenvolvimento de software"

# ── Feeds RSS especializados em dev + IA ──────────────────────────────────────
RSS_FEEDS = [
    "https://hnrss.org/frontpage",
    "https://simonwillison.net/atom/everything/",
    "https://newsletter.pragmaticengineer.com/feed",
    "https://dev.to/feed",
    "https://github.blog/feed/",
    "https://openai.com/news/rss.xml",
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://feed.infoq.com/",
]

# ── Cliente da API Anthropic ──────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── Funções auxiliares ─────────────────────────────────────────────────────────
def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def load_existing() -> dict:
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"articles": [], "last_updated": None}

def save_data(data: dict):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ Salvo: {OUTPUT_FILE}")

def fetch_raw_articles() -> list[dict]:
    raw = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                raw.append({
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", ""))[:800],
                    "source": feed.feed.get("title", url),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"⚠️  Erro ao buscar {url}: {e}")
    return raw

def is_relevant(title: str, summary: str) -> bool:
    keywords = [
        "copilot", "cursor", "claude", "chatgpt", "gpt", "gemini", "codex",
        "devin", "codeium", "tabnine", "supermaven",
        "llm", "ai", "artificial intelligence", "machine learning", "deep learning",
        "neural network", "transformer", "fine-tuning", "rag", "agent",
        "openai", "anthropic", "mistral", "llama", "open source model",
        "developer", "programming", "coding", "software engineer",
        "framework", "library", "api", "sdk", "open source",
        "github", "vscode", "ide", "terminal", "cli",
        "python", "javascript", "typescript", "rust", "go",
        "desenvolvedor", "programação", "inteligência artificial",
        "ferramenta", "código", "software",
    ]
    text = (title + " " + summary).lower()
    return any(kw in text for kw in keywords)

def process_article(raw: dict) -> dict | None:
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
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text)
        if parsed is None:
            return None
        return {
            "id": article_id(raw["url"]),
            "url": raw["url"],
            "source": raw["source"],
            "published": raw["published"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            **parsed,
        }
    except Exception as e:
        print(f"  ⚠️  Erro ao processar '{raw['title'][:50]}': {e}")
        return None

# ── LinkedIn ──────────────────────────────────────────────────────────────────
def post_to_linkedin(article: dict) -> bool:
    """
    Posta o artigo mais relevante no LinkedIn.
    Usa LINKEDIN_ACCESS_TOKEN do ambiente (GitHub Secret).
    """
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token:
        print("⚠️  LINKEDIN_ACCESS_TOKEN não configurado — pulando post LinkedIn")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Obtém o URN do perfil (necessário para identificar o autor do post)
    try:
        me_resp = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=10)
        me_resp.raise_for_status()
        person_id = me_resp.json().get("sub")
        author_urn = f"urn:li:person:{person_id}"
    except Exception as e:
        print(f"⚠️  Erro ao obter perfil LinkedIn: {e}")
        return False

    # Monta o texto do post
    tags_str = " ".join(
        f"#{t.replace(' ', '').replace('-', '')}" for t in article.get("tags", [])[:3]
    )
    post_text = (
        f"🗞️ {article['title']}\n\n"
        f"{article['summary']}\n\n"
        f"{tags_str} #dev #IA #Compilado\n\n"
        f"👉 Leia mais no Compilado — notícias de IA para devs brasileiros:\n"
        f"https://compilado-blush.vercel.app"
    )

    body = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "ARTICLE",
                "media": [
                    {
                        "status": "READY",
                        "description": {"text": article["summary"][:200]},
                        "originalUrl": article["url"],
                        "title": {"text": article["title"]},
                    }
                ],
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    try:
        resp = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        post_id = resp.headers.get("x-restli-id", "?")
        print(f"✅ Postado no LinkedIn! Post ID: {post_id}")
        print(f"   Artigo: {article['title'][:60]}")
        return True
    except requests.HTTPError as e:
        print(f"⚠️  Erro ao postar no LinkedIn: {e}")
        print(f"   Resposta: {e.response.text[:300]}")
        return False
    except Exception as e:
        print(f"⚠️  Erro ao postar no LinkedIn: {e}")
        return False

# ── Função principal ───────────────────────────────────────────────────────────
def run():
    """
    Orquestra o fluxo completo:
    carrega existentes → busca RSS → filtra → processa com IA → salva → posta no LinkedIn
    """
    print(f"\n🤖 Compilado Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("─" * 50)

    data = load_existing()
    existing_ids = {a["id"] for a in data["articles"]}

    print(f"📡 Buscando feeds RSS...")
    raw_articles = fetch_raw_articles()
    print(f"   {len(raw_articles)} artigos encontrados")

    new_raw = [
        r for r in raw_articles
        if article_id(r["url"]) not in existing_ids and is_relevant(r["title"], r["summary"])
    ]
    new_raw = new_raw[:MAX_NEW_PER_RUN]
    print(f"   {len(new_raw)} novos para processar\n")

    processed = []
    for i, raw in enumerate(new_raw, 1):
        print(f"  [{i}/{len(new_raw)}] {raw['title'][:60]}...")
        article = process_article(raw)
        if article and article.get("relevance_score", 0) >= 6:
            processed.append(article)
            print(f"       ✓ Score {article['relevance_score']} | {article['category']}")
        else:
            print(f"       ✗ Irrelevante ou baixo score")

    data["articles"] = (processed + data["articles"])[:MAX_ARTICLES_TOTAL]
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    data["total"] = len(data["articles"])

    save_data(data)
    print(f"\n📰 Total: {data['total']} artigos | 🆕 Adicionados: {len(processed)}")

    if processed:
        git_push(len(processed))

        # Posta o artigo com maior score no LinkedIn
        print("\n🔗 Postando no LinkedIn...")
        best = max(processed, key=lambda a: a.get("relevance_score", 0))
        post_to_linkedin(best)
    else:
        print("⭕  Nenhum artigo novo — git push e LinkedIn ignorados")

def git_push(n_new: int) -> None:
    """
    Faz commit e push do news_data.json atualizado para o GitHub.
    O Vercel detecta o push e atualiza o site automaticamente.
    """
    print("\n🚀 Publicando no GitHub...")
    repo_dir = Path(__file__).parent
    try:
        subprocess.run(["git", "add", "news_data.json"], cwd=repo_dir, check=True)
        msg = f"atualiza noticias: +{n_new} artigos [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"
        subprocess.run(["git", "commit", "-m", msg], cwd=repo_dir, check=True)
        subprocess.run(["git", "push"], cwd=repo_dir, check=True)
        print("✅ Site atualizado no Vercel!")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Git push falhou: {e}")
        print("   O JSON foi salvo localmente. Rode 'git push' manualmente quando possível.")

if __name__ == "__main__":
    run()
