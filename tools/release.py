# -*- coding: utf-8 -*-
"""发版工具：打 tag → 推送到 GitHub → 创建 Release。

沿用项目既有习惯：功能完成即提交，最后一个提交打 `vX.Y.Z` tag 并推送到
GitHub。本脚本把 tag / push / Release 三步串起来，避免手动漏步骤。

用法（项目根目录）：
    python tools\\release.py --version 0.4.3
    python tools\\release.py --version 0.4.3 --title "v0.4.3 眼睛跟随"
    python tools\\release.py --version 0.4.3 --notes-file notes.md
    python tools\\release.py --version 0.4.3 --dry-run      # 只检查不推送

token 来源（按优先级）：
  1. 环境变量 GITHUB_TOKEN
  2. ~/.git-credentials 里首个 https://...@github.com 条目（git store 格式）
只用于调 GitHub API 创建 Release；push 本身走 git 的 credential helper。

网络：脚本自动读取 HTTPS_PROXY / HTTP_PROXY（urllib 原生支持），
走代理时不需额外参数。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# git 可执行文件：优先 PATH，其次 Git for Windows 的默认安装位置
GIT_FALLBACKS = (r"C:\Program Files\Git\cmd\git.exe",
                 r"C:\Program Files (x86)\Git\cmd\git.exe")


def git_exe() -> str:
    """定位 git：PATH 找不到时退回安装目录（本机 PATH 可能未刷新）。"""
    found = shutil.which("git")
    if found:
        return found
    for path in GIT_FALLBACKS:
        if Path(path).exists():
            return path
    sys.exit("找不到 git，请先安装 Git for Windows")


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """在项目根目录执行命令，返回 CompletedProcess（文本模式）。"""
    proc = subprocess.run([git_exe(), *args], cwd=str(ROOT),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        sys.exit(f"git {' '.join(args)} 失败：\n{proc.stderr.strip()}")
    return proc


def repo_slug() -> tuple[str, str]:
    """从 origin 远端地址解析 (owner, repo)。"""
    url = run(["remote", "get-url", "origin"]).stdout.strip()
    m = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", url)
    if not m:
        sys.exit(f"无法从 origin 解析 GitHub 仓库：{url}")
    return m.group("owner"), m.group("repo")


def read_token() -> str | None:
    """环境变量优先，其次 git store 的 ~/.git-credentials。"""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    cred = Path.home() / ".git-credentials"
    if cred.exists():
        for line in cred.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"https://[^:@/]+:(?P<token>[^@]+)@github\.com", line.strip())
            if m:
                return m.group("token")
    return None


def api(path: str, token: str, payload: dict | None = None) -> dict:
    """调 GitHub API（POST 用 payload，GET 传 None）。"""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        API + path, data=data,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "xiaoliang-release",
                 "Content-Type": "application/json"},
        method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"GitHub API {exc.code}：{body}")
    except urllib.error.URLError as exc:
        sys.exit(f"连接 GitHub 失败（如需代理请设置 HTTPS_PROXY）：{exc.reason}")


def default_notes(version: str) -> str:
    """默认说明：取该 tag 之前的全部提交标题，按类型分节。"""
    log = run(["log", "--pretty=%s", f"v{version}^..HEAD"], check=False)
    if log.returncode != 0:      # 该版本尚无 tag，退回最近一次提交范围
        log = run(["log", "--pretty=%s", "-20"])
    lines = [ln.strip() for ln in log.stdout.splitlines() if ln.strip()]
    groups = {"feat": [], "fix": [], "perf": [], "refactor": [], "docs": [], "其他": []}
    for ln in lines:
        m = re.match(r"(feat|fix|perf|refactor|docs|build|test|chore)", ln)
        key = m.group(1) if m else "其他"
        groups.setdefault(key, groups["其他"]).append(ln)
    titles = {"feat": "新功能", "fix": "修复", "perf": "性能",
              "refactor": "重构", "docs": "文档",
              "build": "构建", "test": "测试", "chore": "杂项", "其他": "其他"}
    parts = [f"## {titles.get(k, k)}\n" + "\n".join(f"- {x}" for x in v)
             for k, v in groups.items() if v]
    return "\n\n".join(parts) if parts else "本次发布。"


def main() -> int:
    ap = argparse.ArgumentParser(description="小凉发版：tag + push + Release")
    ap.add_argument("--version", required=True, help="版本号，如 0.4.3（不带 v）")
    ap.add_argument("--title", help="Release 标题，默认 v<version>")
    ap.add_argument("--notes-file", help="发布说明 markdown 文件路径")
    ap.add_argument("--dry-run", action="store_true", help="只做检查，不推送")
    ap.add_argument("--skip-release", action="store_true",
                    help="只打 tag + push，不创建 GitHub Release")
    args = ap.parse_args()

    version = args.version.lstrip("v")
    if not VERSION_RE.match(version):
        sys.exit(f"版本号格式应为 X.Y.Z：{args.version}")
    tag = f"v{version}"

    # ── 前置检查 ──
    if run(["status", "--porcelain"]).stdout.strip():
        sys.exit("工作区有未提交改动，先提交再发版（git add -A && git commit）")
    if run(["tag", "-l", tag]).stdout.strip():
        sys.exit(f"tag {tag} 已存在，换一个版本号")
    branch = run(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    print(f"分支 {branch}，HEAD {run(['log', '-1', '--pretty=%h %s']).stdout.strip()}")

    notes = (Path(args.notes_file).read_text(encoding="utf-8")
             if args.notes_file else default_notes(version))
    title = args.title or tag

    if args.dry_run:
        print(f"\n[dry-run] 将创建 tag {tag}，标题「{title}」，说明：\n{notes}")
        return 0

    # ── tag + push ──
    run(["tag", "-a", tag, "-m", f"release {tag}"])
    print(f"已创建 tag {tag}")
    run(["push", "origin", branch])
    run(["push", "origin", tag])
    print(f"已推送 {branch} 与 {tag}")

    if args.skip_release:
        return 0

    # ── GitHub Release ──
    token = read_token()
    if not token:
        print("未找到 GITHUB_TOKEN 或 ~/.git-credentials，跳过创建 Release",
              file=sys.stderr)
        return 0
    owner, repo = repo_slug()
    result = api(f"/repos/{owner}/{repo}/releases", token,
                 {"tag_name": tag, "name": title, "body": notes, "draft": False})
    print(f"Release 已发布：{result.get('html_url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
