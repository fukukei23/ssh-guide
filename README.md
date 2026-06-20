# Android SSH接続ガイド

スマホからPC（WSL2）上のClaude Code CLIを操作するためのSSH接続ガイド。
Tailscale VPN + Termux + SSH + tmux の組み合わせ。

## 公開URL

https://fukukei23.github.io/ssh-guide/

## 構成

- `source/*.md` — 唯一のマスター（手書き）
- `convert.py` — Markdown → HTML 変換スクリプト
- `docs/` — GitHub Pages 公開用HTML（convert.py で自動生成）

## 更新手順

1. `source/*.md` を編集
2. `python3 convert.py` で `docs/` を再生成
3. `git add -A && git commit -m "..." && git push`

## 関連

- guide-builder スキルによる convert.py パイプライン
- 元ネタ: ssot-guide / claude-code-guide
