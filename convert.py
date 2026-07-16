#!/usr/bin/env python3
"""Android SSHガイド: Markdown → モバイル最適化HTML変換スクリプト."""

import re
import unicodedata
from datetime import date
from pathlib import Path

from jinja2 import Template
from markdown_it import MarkdownIt

# --- 設定 ---

SOURCE_DIR = Path(__file__).parent / "source"
OUTPUT_DIR = Path(__file__).parent / "docs"
VERSION_FILE = Path(__file__).parent / "VERSION"


# --- バージョン管理 ---

def _read_version() -> str:
    """VERSIONファイルを読み込む。なければ '1.0' を返す。"""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "1.0"


def _bump_version(version: str) -> str:
    """マイナーバージョンをインクリメント: '1.3' → '1.4'"""
    parts = version.split(".")
    major = parts[0]
    minor = int(parts[1]) if len(parts) > 1 else 0
    return f"{major}.{minor + 1}"


def get_build_info() -> tuple[str, str]:
    """(version_str, date_str) を返す。ビルドごとにマイナーをインクリメント。"""
    current = _read_version()
    new_version = _bump_version(current)
    VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")
    today = date.today().strftime("%Y.%m.%d")
    return new_version, today

# 既存章の手動定義
CHAPTER_MAP = {
    "00_概要.md": {"slug": "00-overview", "title": "概要", "icon": "📋", "desc": "使い方・前提条件・デバイス一覧"},
    "01_初回セットアップ.md": {"slug": "01-setup", "title": "初回セットアップ", "icon": "🔧", "desc": "蓋閉じ・Tailscale・Termux・SSH鍵・tmux起動（約15分）"},
    "02_毎回の手順.md": {"slug": "02-daily", "title": "毎回の手順", "icon": "🔁", "desc": "ssh接続・tmux操作・切断のクイックリファレンス"},
    "03_PC側ヘルスチェック.md": {"slug": "03-healthcheck", "title": "PC側ヘルスチェック", "icon": "🩺", "desc": "Tailscale状態・sshd LISTEN・スリープ設定の診断"},
    "04_トラブル対応.md": {"slug": "04-troubleshooting", "title": "トラブル対応", "icon": "🆘", "desc": "password/Connection refused/timeout等のFAQ"},
    "05_スマホからPCへの引き継ぎ.md": {"slug": "05-handoff", "title": "スマホからPCへの引き継ぎ", "icon": "🔄", "desc": "外出先の作業をPCの大画面で続きから・同時ミラーリングも"},
    "06_リモート運用のベストプラクティス.md": {"slug": "06-best-practices", "title": "リモート運用のベストプラクティス", "icon": "🛡️", "desc": "紛失時revoke・再起動復旧・TermuxのCtrl+B・KeepAlive・MagicDNS"},
}


# --- 自動スキャン ---

def _filename_to_slug(filename: str) -> str:
    """ファイル名からslugを生成: '13_glm-rate-proxy.md' → '13-glm-rate-proxy'"""
    stem = Path(filename).stem  # 拡張子除去
    # 先頭の数字+区切り文字を抽出: "13_foo" → "13-foo", "00_早見表" → "00-cheatsheet相当"
    # アンダースコアをハイフンに、日本語はASCIIに変換できないのでそのまま残す
    slug = stem.replace("_", "-", 1)  # 最初の _ のみハイフン化
    # 残りの _ もハイフン化
    slug = slug.replace("_", "-")
    # ASCII以外の文字を除去してslugを作る
    ascii_slug = ""
    for ch in slug:
        if ch.isascii():
            ascii_slug += ch.lower()
        elif ch == "-":
            ascii_slug += "-"
    # 連続ハイフン・末尾ハイフンを整理
    ascii_slug = re.sub(r"-+", "-", ascii_slug).strip("-")
    return ascii_slug or slug


def _extract_frontmatter(text: str) -> tuple[dict, str]:
    """YAMLフロントマターを抽出。なければ空dictとテキストをそのまま返す。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, body


def _extract_title_from_h1(text: str) -> str:
    """H1ヘッダーからタイトルを抽出。'# 13 GLM Rate Proxy — ...' → 'GLM Rate Proxy'"""
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            # 番号プレフィックスを除去: "13 GLM Rate Proxy" → "GLM Rate Proxy"
            title = re.sub(r"^\d+\s+", "", title)
            # ダッシュ以降の説明を除去: "GLM Rate Proxy — 説明" → "GLM Rate Proxy"
            title = re.split(r"\s+[—–-]\s+", title)[0].strip()
            return title
    return ""


def _extract_desc_from_h1(text: str) -> str:
    """H1ヘッダーのダッシュ以降を説明として抽出。"""
    for line in text.splitlines():
        if line.startswith("# "):
            parts = re.split(r"\s+[—–-]\s+", line[2:].strip(), maxsplit=1)
            if len(parts) > 1:
                return parts[1].strip()
    return ""


def build_chapter_map() -> dict:
    """source/ をスキャンして完全なCHAPTER_MAPを構築。
    CHAPTER_MAPに未登録のファイルは自動検出して追加する。"""
    result = dict(CHAPTER_MAP)

    for md_file in sorted(SOURCE_DIR.glob("*.md")):
        filename = md_file.name
        if filename.startswith("_"):
            continue  # _README.md等は除外
        if filename in result:
            continue  # 既登録はスキップ

        text = md_file.read_text(encoding="utf-8")
        meta, body = _extract_frontmatter(text)

        title = meta.get("title") or _extract_title_from_h1(text) or Path(filename).stem
        desc = meta.get("card_desc") or meta.get("desc") or _extract_desc_from_h1(text) or title
        icon = meta.get("icon", "📄")
        slug = meta.get("slug") or _filename_to_slug(filename)

        result[filename] = {"slug": slug, "title": title, "icon": icon, "desc": desc}
        print(f"AUTO: {filename} → {slug} ({title})")

    return result

REMOVE_SECTIONS: list[str] = []
REMOVE_PATTERNS: list[str] = []
INLINE_REPLACEMENTS: list[tuple[str, str]] = []
TABLE_COL_SANITIZE: list[tuple[str, str]] = []

MERMAID_DIAGRAMS: dict[str, list[tuple[str, str]]] = {}

# --- HTMLテンプレート ---

CHAPTER_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="ja" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} — Android SSHガイド</title>
    <meta name="description" content="スマホからPCのClaude Codeを操作するSSH接続ガイド — {{ title }}">
    <meta property="og:title" content="{{ title }} — Android SSHガイド">
    <meta property="og:description" content="スマホからPCのClaude Codeを操作するSSH接続ガイド — {{ title }}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="https://fukukei23.github.io/ssh-guide/chapters/{{ slug }}.html">
    <meta property="og:image" content="https://fukukei23.github.io/ssh-guide/assets/ogp.png">
    <meta name="twitter:card" content="summary_large_image">
    <link rel="stylesheet" href="../assets/style.css">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📱</text></svg>">
</head>
<body>
    <header class="site-header">
        <button class="menu-toggle" aria-label="メニュー" id="menuToggle">
            <span></span><span></span><span></span>
        </button>
        <a href="../index.html" class="site-title">📱 Android SSHガイド</a>
        <button class="theme-toggle" id="themeToggle" aria-label="テーマ切替">
            <span class="icon-light">☀️</span>
            <span class="icon-dark">🌙</span>
        </button>
    </header>

    <nav class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <a href="../index.html">🏠 ホーム</a>
        </div>
        {% for ch in chapters %}
        <a href="{{ ch.slug }}.html"
           class="sidebar-link{{ ' active' if ch.slug == current_slug }}">
            <span class="sidebar-icon">{{ ch.icon }}</span>
            {{ ch.title }}
        </a>
        {% endfor %}
    </nav>
    <div class="sidebar-overlay" id="sidebarOverlay"></div>

    <main class="content">
        <div class="chapter-nav-top">
            {% if prev_ch %}
            <a href="{{ prev_ch.slug }}.html" class="nav-prev">← {{ prev_ch.title }}</a>
            {% endif %}
            {% if next_ch %}
            <a href="{{ next_ch.slug }}.html" class="nav-next">{{ next_ch.title }} →</a>
            {% endif %}
        </div>

        <article class="chapter-body">
            {{ content|safe }}
        </article>

        <nav class="chapter-nav-bottom">
            {% if prev_ch %}
            <a href="{{ prev_ch.slug }}.html" class="nav-card prev">
                <span class="nav-label">← 前の章</span>
                <span class="nav-title">{{ prev_ch.icon }} {{ prev_ch.title }}</span>
            </a>
            {% endif %}
            {% if next_ch %}
            <a href="{{ next_ch.slug }}.html" class="nav-card next">
                <span class="nav-label">次の章 →</span>
                <span class="nav-title">{{ next_ch.icon }} {{ next_ch.title }}</span>
            </a>
            {% endif %}
        </nav>
    </main>

    <footer class="site-footer">
        <p>Android SSHガイド — <a href="https://github.com/fukukei23/ssh-guide">GitHub</a>
         · <a href="https://fukukei23.github.io/claude-code-guide/">Claude Code Guide</a>
         · <a href="https://fukukei23.github.io/guides/">技術ガイド集</a>
         · <a href="https://fukukei23.github.io/">fukukei23</a></p>
        <p class="site-version">v{{ version }} · {{ build_date }}</p>
    </footer>

    <script src="../assets/script.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'default',
            themeVariables: { fontSize: '14px' }
        });
    </script>
</body>
</html>
""", autoescape=True)

INDEX_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="ja" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Android SSH接続ガイド — スマホからClaude Codeを操作</title>
    <meta name="description" content="スマホからPC（WSL2）上のClaude Code CLIを操作するSSH接続完全ガイド">
    <meta property="og:title" content="Android SSH接続ガイド">
    <meta property="og:description" content="スマホからPC（WSL2）上のClaude Code CLIを操作するSSH接続完全ガイド">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://fukukei23.github.io/ssh-guide/">
    <meta property="og:image" content="https://fukukei23.github.io/ssh-guide/assets/ogp.png">
    <meta name="twitter:card" content="summary_large_image">
    <link rel="stylesheet" href="assets/style.css">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📱</text></svg>">
</head>
<body class="index-page">
    <header class="site-header">
        <span class="site-title">📱 Android SSHガイド</span>
        <button class="theme-toggle" id="themeToggle" aria-label="テーマ切替">
            <span class="icon-light">☀️</span>
            <span class="icon-dark">🌙</span>
        </button>
    </header>

    <main class="content">
        <section class="hero">
            <h1>Android SSH接続ガイド</h1>
            <p>スマホからPC（WSL2）のClaude Codeを操作する<br>Tailscale + Termux + SSH + tmux 完全ガイド</p>
        </section>

        <section class="chapter-grid">
            {% for ch in chapters %}
            <a href="chapters/{{ ch.slug }}.html" class="chapter-card">
                <div class="card-icon">{{ ch.icon }}</div>
                <div class="card-number">第{{ ch.number }}章</div>
                <h2 class="card-title">{{ ch.title }}</h2>
                <p class="card-desc">{{ ch.desc }}</p>
            </a>
            {% endfor %}
        </section>

        <section class="features">
            <h2>📖 このガイドの特徴</h2>
            <div class="feature-grid">
                <div class="feature-item">
                    <span class="feature-icon">📱</span>
                    <h3>スマホから操作</h3>
                    <p>Android + Termux から外出先でもPCのClaude Codeを操作</p>
                </div>
                <div class="feature-item">
                    <span class="feature-icon">🔐</span>
                    <h3>鍵認証で安全</h3>
                    <p>ed25519 鍵でパスワード不要・Tailscale VPN経由で暗号化</p>
                </div>
                <div class="feature-item">
                    <span class="feature-icon">🔄</span>
                    <h3>tmuxで常駐</h3>
                    <p>セッションを維持したまま接続切断可能・復帰も一瞬</p>
                </div>
                <div class="feature-item">
                    <span class="feature-icon">🩺</span>
                    <h3>トラブル対応</h3>
                    <p>PC側ヘルスチェック手順とFAQでつながらない時も即解決</p>
                </div>
            </div>
        </section>
    </main>

    <footer class="site-footer">
        <p>Android SSHガイド — <a href="https://github.com/fukukei23/ssh-guide">GitHub</a>
         · <a href="https://fukukei23.github.io/claude-code-guide/">Claude Code Guide</a>
         · <a href="https://fukukei23.github.io/guides/">技術ガイド集</a>
         · <a href="https://fukukei23.github.io/">fukukei23</a></p>
        <p class="site-version">v{{ version }} · {{ build_date }}</p>
    </footer>

    <script src="assets/script.js"></script>
</body>
</html>
""", autoescape=True)


# --- フィルタリング ---

def filter_sections(text: str) -> str:
    """個人情報・環境固有セクションを除去."""
    lines = text.split("\n")
    result = []
    skip = False

    for line in lines:
        stripped = line.strip()

        # 除去対象セクションの開始（## または ### セクション）
        if stripped.startswith("## ") and any(stripped.startswith(s) for s in REMOVE_SECTIONS):
            skip = True
            continue

        # 「あなたの」で始まる## / ### セクションも除去
        if (stripped.startswith("## ") or stripped.startswith("### ")) and any(p in stripped for p in REMOVE_PATTERNS):
            skip = True
            continue

        # 次の ## セクションでスキップ解除（### はスキップ解除しない）
        if skip and stripped.startswith("## ") and not any(p in stripped for p in REMOVE_PATTERNS):
            skip = False

        if not skip:
            result.append(line)

    text = "\n".join(result)

    # 個人識別子のサニタイズ（ssh-guideはパブリック公開コンテンツのため不要）
    pass

    # インライン個人情報のサニタイズ
    for pattern, replacement in INLINE_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    for pattern, replacement in TABLE_COL_SANITIZE:
        text = re.sub(pattern, replacement, text)

    # 未処理の「あなたの」を行内テキストから除去
    text = re.sub(r"あなたの環境では", "", text)
    text = re.sub(r"あなたの環境:", "", text)

    return text


# --- Markdown → HTML変換 ---

def convert_md_to_html(md_text: str) -> str:
    """MarkdownをHTMLに変換."""
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    return md.render(md_text)


def inject_mermaid(html: str, filename: str) -> str:
    """Mermaid図を指定位置に挿入."""
    diagrams = MERMAID_DIAGRAMS.get(filename, [])
    if not diagrams:
        return html

    for heading, diagram_code in diagrams:
        # HTMLの見出しタグを検索（<a id>タグ込みも対応）
        heading_text = heading.replace("## ", "").strip()
        mermaid_block = (
            f'<div class="mermaid-wrapper">'
            f'<div class="mermaid">\n{diagram_code}\n</div>'
            f'</div>'
        )

        # <h2>テキスト</h2> または <h2><a ...></a>テキスト</h2> の前に挿入
        pattern = f"(<h2>(?:<a[^>]*></a>)?{re.escape(heading_text)}</h2>)"
        if re.search(pattern, html):
            html = re.sub(pattern, mermaid_block + r"\1", html, count=1)

    return html


def rewrite_links(html: str, chapter_map: dict | None = None) -> str:
    """内部リンクをHTML URLに書き換え."""
    from urllib.parse import quote, unquote

    cmap = chapter_map or CHAPTER_MAP

    for filename, info in cmap.items():
        # [テキスト](XX_YY.md) → XX-yy.html
        html = html.replace(f'href="{filename}', f'href="{info["slug"]}.html')
        # [テキスト](XX_YY.md#anchor) → XX-yy.html#anchor
        html = re.sub(
            rf'href="{re.escape(filename)}#',
            f'href="{info["slug"]}.html#',
            html,
        )

        # URLエンコードされたリンク（例: 11_%E7%8F%BE%E5%A0%B4...）も処理
        encoded_name = quote(filename, safe='')
        if encoded_name != filename:
            html = html.replace(f'href="{encoded_name}', f'href="{info["slug"]}.html')
            html = re.sub(
                rf'href="{re.escape(encoded_name)}#',
                f'href="{info["slug"]}.html#',
                html,
            )

    # 未変換の.mdリンクをすべて処理
    def replace_md_link(match):
        href = match.group(1)
        for filename, info in cmap.items():
            decoded = unquote(href)
            if filename in decoded or filename in href:
                anchor = ""
                if "#" in href:
                    anchor = "#" + href.split("#", 1)[1]
                elif "#" in decoded:
                    anchor = "#" + decoded.split("#", 1)[1]
                return f'href="{info["slug"]}.html{anchor}"'
        return f'href="#"'

    html = re.sub(r'href="([^"]*\.md[^"]*)"', replace_md_link, html)

    # 外部リンク（obsidian-ssot内の他ファイル）を除去
    html = re.sub(r'href="\.\./[^"]*"', 'href="#"', html)
    html = re.sub(r'href="01_DECISIONS[^"]*"', 'href="#"', html)

    return html


def convert_tldr(html: str) -> str:
    """H1直後の『3行で分かる』blockquote を <aside class="tldr"> に変換.

    平易化（2026-07-17移植）: 各ページH1直後に置いた `> **3行で分かる**` blockquoteを
    目立つTLDR枠に変換する。enhance_html の単一段落callout変換（<blockquote><p>…</p></blockquote>）
    にマッチしない複数要素blockquoteを対象とするため、enhance_html の後に呼ぶこと。
    H1直後の最初のblockquoteのみ（位置保証）。'3行で分かる' を含まなければ変換しない（後方互換）。
    ※ enhance_html の【前】に呼ぶこと（後だと enhance_html のcallout変換にTLDRが食われる）。
    """
    pattern = re.compile(
        r'(<h1[^>]*>.*?</h1>\s*)(<blockquote>.*?</blockquote>)',
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return html
    head, block = m.group(1), m.group(2)
    if '3行で分かる' not in block:
        return html
    inner = block[len('<blockquote>'):-len('</blockquote>')]
    converted = head + f'<aside class="tldr">{inner}</aside>'
    return html[:m.start()] + converted + html[m.end():]


def enhance_html(html: str) -> str:
    """HTMLに装飾を追加（テーブルラップ・コールアウト等）."""
    # テーブルをスクロールラッパーで囲む
    html = re.sub(
        r"(<table[^>]*>.*?</table>)",
        r'<div class="table-wrapper">\1</div>',
        html,
        flags=re.DOTALL,
    )

    # 引用ブロックをコールアウトに変換
    def callout_replace(match):
        content = match.group(1)
        if "注意" in content or "⚠" in content:
            return f'<div class="callout callout-warn"><p>{content}</p></div>'
        if "重要" in content:
            return f'<div class="callout callout-danger"><p>{content}</p></div>'
        if "現場の知見" in content or "💡" in content or "Tip" in content:
            return f'<div class="callout callout-tip"><p>{content}</p></div>'
        return f'<div class="callout callout-info"><p>{content}</p></div>'

    html = re.sub(r"<blockquote>\s*<p>(.*?)</p>\s*</blockquote>", callout_replace, html, flags=re.DOTALL)

    return html


# --- メイン ---

def main():
    # ディレクトリ準備
    chapters_dir = OUTPUT_DIR / "chapters"
    assets_dir = OUTPUT_DIR / "assets"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    # バージョン・日付を取得（ビルドごとにインクリメント）
    version, build_date = get_build_info()
    print(f"Build: v{version} · {build_date}")

    # 章リストを構築（自動スキャン込み）
    effective_map = build_chapter_map()
    chapters = []
    for filename, info in sorted(effective_map.items()):
        chapters.append({
            "number": info["slug"][:2],
            "slug": info["slug"],
            "title": info["title"],
            "icon": info["icon"],
            "desc": info["desc"],
            "filename": filename,
        })

    # 各章を変換
    for i, ch in enumerate(chapters):
        src = SOURCE_DIR / ch["filename"]
        if not src.exists():
            print(f"SKIP: {ch['filename']} not found")
            continue

        md_text = src.read_text(encoding="utf-8")
        md_text = filter_sections(md_text)
        html_body = convert_md_to_html(md_text)
        html_body = inject_mermaid(html_body, ch["filename"])
        html_body = rewrite_links(html_body, effective_map)
        html_body = convert_tldr(html_body)
        html_body = enhance_html(html_body)

        prev_ch = chapters[i - 1] if i > 0 else None
        next_ch = chapters[i + 1] if i < len(chapters) - 1 else None

        full_html = CHAPTER_TEMPLATE.render(
            title=ch["title"],
            slug=ch["slug"],
            current_slug=ch["slug"],
            content=html_body,
            chapters=chapters,
            prev_ch=prev_ch,
            next_ch=next_ch,
            version=version,
            build_date=build_date,
        )

        out = chapters_dir / f"{ch['slug']}.html"
        out.write_text(full_html, encoding="utf-8")
        print(f"OK: {ch['slug']}.html")

    # index.html 生成
    index_html = INDEX_TEMPLATE.render(chapters=chapters, version=version, build_date=build_date)
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print("OK: index.html")

    print(f"\n完了: {len(chapters)}章 + index → {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
