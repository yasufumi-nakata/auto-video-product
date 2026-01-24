"""
GitHub リポジトリ変更点取得モジュール
eegflow.jp の GitHub リポジトリから前日の変更点を取得
"""
import os
import requests
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "eegflow/eegflow.jp")  # owner/repo 形式


def get_headers():
    """GitHub API用のヘッダーを返す"""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def fetch_commits_from_git(repo, days_back=1):
    """
    Fallback: fetch commits via git when API is rate-limited.
    """
    if not repo or "/" not in repo:
        print(f"Warning: Invalid repo format '{repo}'. Expected owner/repo.")
        return []

    repo_url = f"https://github.com/{repo}.git"
    cache_root = os.path.expanduser("~/.cache/auto-video-product/github")
    repo_dir = os.path.join(cache_root, repo.replace("/", "_"))

    try:
        os.makedirs(cache_root, exist_ok=True)
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            subprocess.run(
                ["git", "clone", "--no-tags", "--depth", "200", repo_url, repo_dir],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
        else:
            subprocess.run(
                ["git", "fetch", "--no-tags", "--depth", "200", "origin", "+refs/heads/*:refs/remotes/origin/*"],
                check=True,
                cwd=repo_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

        head_ref = "origin/HEAD"
        head_result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if head_result.returncode == 0 and head_result.stdout.strip():
            head_ref = head_result.stdout.strip()

        since = (datetime.now() - timedelta(days=days_back)).isoformat()
        log_result = subprocess.run(
            [
                "git",
                "log",
                head_ref,
                f"--since={since}",
                "--pretty=format:%H%x1f%an%x1f%aI%x1f%s%x1e"
            ],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if log_result.returncode != 0:
            print(f"Warning: git log failed: {log_result.stderr.strip()}")
            return []

        output = log_result.stdout.strip("\n\x1e")
        if not output:
            return []

        result = []
        for record in output.split("\x1e"):
            if not record:
                continue
            parts = record.split("\x1f")
            if len(parts) != 4:
                continue
            sha, author, date, message = parts
            result.append({
                "sha": sha[:7],
                "message": message,
                "author": author,
                "date": date,
                "url": f"https://github.com/{repo}/commit/{sha}",
                "files_changed": []
            })
        return result
    except Exception as e:
        print(f"Error fetching commits via git: {e}")
        return []


def fetch_commits(repo=None, days_back=1):
    """
    前日のコミットを取得

    Args:
        repo: リポジトリ名 (owner/repo 形式)
        days_back: 何日前までのコミットを取得するか

    Returns:
        list: コミット情報のリスト
    """
    if repo is None:
        repo = GITHUB_REPO

    since = (datetime.now() - timedelta(days=days_back)).isoformat() + "Z"
    until = datetime.now().isoformat() + "Z"

    url = f"https://api.github.com/repos/{repo}/commits"
    params = {
        "since": since,
        "until": until,
        "per_page": 100
    }

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=30)
        response.raise_for_status()
        commits = response.json()

        result = []
        for commit in commits:
            commit_data = commit.get("commit", {})
            author = commit_data.get("author", {})

            # コミットの詳細を取得（変更ファイルなど）
            detail_url = commit.get("url")
            files_changed = []
            if detail_url:
                try:
                    detail_response = requests.get(detail_url, headers=get_headers(), timeout=10)
                    if detail_response.status_code == 200:
                        detail = detail_response.json()
                        files_changed = [f.get("filename", "") for f in detail.get("files", [])]
                except Exception:
                    pass

            result.append({
                "sha": commit.get("sha", "")[:7],
                "message": commit_data.get("message", ""),
                "author": author.get("name", "Unknown"),
                "date": author.get("date", ""),
                "url": commit.get("html_url", ""),
                "files_changed": files_changed
            })

        return result
    except requests.exceptions.HTTPError as e:
        response = e.response
        if response is not None and response.status_code == 403 and "rate limit" in response.text.lower():
            print("Warning: GitHub API rate limit hit. Falling back to git.")
            return fetch_commits_from_git(repo, days_back)
        print(f"Error fetching commits: {e}")
        return []
    except Exception as e:
        print(f"Error fetching commits: {e}")
        return []


def fetch_pull_requests(repo=None, days_back=1, state="all"):
    """
    前日のプルリクエストを取得

    Args:
        repo: リポジトリ名 (owner/repo 形式)
        days_back: 何日前までのPRを取得するか
        state: PRの状態 (open, closed, all)

    Returns:
        list: PR情報のリスト
    """
    if repo is None:
        repo = GITHUB_REPO

    since = datetime.now() - timedelta(days=days_back)

    url = f"https://api.github.com/repos/{repo}/pulls"
    params = {
        "state": state,
        "sort": "updated",
        "direction": "desc",
        "per_page": 50
    }

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=30)
        response.raise_for_status()
        prs = response.json()

        result = []
        for pr in prs:
            updated_at = pr.get("updated_at", "")
            if updated_at:
                try:
                    pr_date = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
                    if pr_date < since:
                        continue
                except ValueError:
                    pass

            # PR本文を取得
            body = pr.get("body", "") or ""

            result.append({
                "number": pr.get("number"),
                "title": pr.get("title", ""),
                "body": body[:2000] if len(body) > 2000 else body,
                "state": pr.get("state", ""),
                "author": pr.get("user", {}).get("login", "Unknown"),
                "created_at": pr.get("created_at", ""),
                "updated_at": updated_at,
                "merged_at": pr.get("merged_at"),
                "url": pr.get("html_url", ""),
                "labels": [label.get("name", "") for label in pr.get("labels", [])]
            })

        return result
    except Exception as e:
        print(f"Error fetching pull requests: {e}")
        return []


def fetch_issues(repo=None, days_back=1, state="all"):
    """
    前日のIssueを取得

    Args:
        repo: リポジトリ名 (owner/repo 形式)
        days_back: 何日前までのIssueを取得するか
        state: Issueの状態 (open, closed, all)

    Returns:
        list: Issue情報のリスト
    """
    if repo is None:
        repo = GITHUB_REPO

    since = (datetime.now() - timedelta(days=days_back)).isoformat() + "Z"

    url = f"https://api.github.com/repos/{repo}/issues"
    params = {
        "state": state,
        "since": since,
        "sort": "updated",
        "direction": "desc",
        "per_page": 50
    }

    try:
        response = requests.get(url, headers=get_headers(), params=params, timeout=30)
        response.raise_for_status()
        issues = response.json()

        result = []
        for issue in issues:
            # PRはスキップ（PRもIssue APIに含まれるため）
            if issue.get("pull_request"):
                continue

            body = issue.get("body", "") or ""

            # Issueのコメントを取得
            comments = []
            comments_url = issue.get("comments_url")
            if comments_url and issue.get("comments", 0) > 0:
                try:
                    comments_response = requests.get(comments_url, headers=get_headers(), timeout=10)
                    if comments_response.status_code == 200:
                        for comment in comments_response.json()[-5:]:  # 最新5件
                            comment_body = comment.get("body", "")
                            if comment_body:
                                comments.append({
                                    "author": comment.get("user", {}).get("login", "Unknown"),
                                    "body": comment_body[:500] if len(comment_body) > 500 else comment_body,
                                    "created_at": comment.get("created_at", "")
                                })
                except Exception:
                    pass

            result.append({
                "number": issue.get("number"),
                "title": issue.get("title", ""),
                "body": body[:2000] if len(body) > 2000 else body,
                "state": issue.get("state", ""),
                "author": issue.get("user", {}).get("login", "Unknown"),
                "created_at": issue.get("created_at", ""),
                "updated_at": issue.get("updated_at", ""),
                "closed_at": issue.get("closed_at"),
                "url": issue.get("html_url", ""),
                "labels": [label.get("name", "") for label in issue.get("labels", [])],
                "comments": comments
            })

        return result
    except Exception as e:
        print(f"Error fetching issues: {e}")
        return []


def fetch_discussions(repo=None, days_back=1):
    """
    前日のDiscussionを取得（GraphQL API使用）

    Args:
        repo: リポジトリ名 (owner/repo 形式)
        days_back: 何日前までのDiscussionを取得するか

    Returns:
        list: Discussion情報のリスト
    """
    if repo is None:
        repo = GITHUB_REPO

    if not GITHUB_TOKEN:
        print("Warning: GITHUB_TOKEN required for Discussions API")
        return []

    if "/" not in repo:
        print(f"Warning: Invalid repo format '{repo}'. Expected owner/repo.")
        return []
    owner, repo_name = repo.split("/", 1)
    if not owner or not repo_name:
        print(f"Warning: Invalid repo format '{repo}'. Expected owner/repo.")
        return []
    since = datetime.now() - timedelta(days=days_back)

    query = """
    query($owner: String!, $repo: String!, $first: Int!) {
        repository(owner: $owner, name: $repo) {
            discussions(first: $first, orderBy: {field: UPDATED_AT, direction: DESC}) {
                nodes {
                    number
                    title
                    body
                    author { login }
                    createdAt
                    updatedAt
                    url
                    category { name }
                    comments(first: 5) {
                        nodes {
                            author { login }
                            body
                            createdAt
                        }
                    }
                }
            }
        }
    }
    """

    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=get_headers(),
            json={"query": query, "variables": {"owner": owner, "repo": repo_name, "first": 20}},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        discussions = data.get("data", {}).get("repository", {}).get("discussions", {}).get("nodes", [])

        result = []
        for disc in discussions:
            updated_at = disc.get("updatedAt", "")
            if updated_at:
                try:
                    disc_date = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
                    if disc_date < since:
                        continue
                except ValueError:
                    pass

            body = disc.get("body", "") or ""

            comments = []
            for comment in disc.get("comments", {}).get("nodes", []):
                comment_body = comment.get("body", "")
                if comment_body:
                    comments.append({
                        "author": comment.get("author", {}).get("login", "Unknown"),
                        "body": comment_body[:500] if len(comment_body) > 500 else comment_body,
                        "created_at": comment.get("createdAt", "")
                    })

            result.append({
                "number": disc.get("number"),
                "title": disc.get("title", ""),
                "body": body[:2000] if len(body) > 2000 else body,
                "author": disc.get("author", {}).get("login", "Unknown"),
                "created_at": disc.get("createdAt", ""),
                "updated_at": updated_at,
                "url": disc.get("url", ""),
                "category": disc.get("category", {}).get("name", ""),
                "comments": comments
            })

        return result
    except Exception as e:
        print(f"Error fetching discussions: {e}")
        return []


def fetch_all_activities(repo=None, days_back=1):
    """
    リポジトリの全アクティビティを取得

    Args:
        repo: リポジトリ名 (owner/repo 形式)
        days_back: 何日前までのアクティビティを取得するか

    Returns:
        dict: 各種アクティビティの辞書
    """
    if repo is None:
        repo = GITHUB_REPO

    print(f"Fetching GitHub activities for: {repo} (days_back={days_back})")

    commits = fetch_commits(repo, days_back)
    print(f"Commits: {len(commits)}")

    pull_requests = fetch_pull_requests(repo, days_back)
    print(f"Pull Requests: {len(pull_requests)}")

    issues = fetch_issues(repo, days_back)
    print(f"Issues: {len(issues)}")

    discussions = fetch_discussions(repo, days_back)
    print(f"Discussions: {len(discussions)}")

    return {
        "repo": repo,
        "commits": commits,
        "pull_requests": pull_requests,
        "issues": issues,
        "discussions": discussions
    }


if __name__ == "__main__":
    activities = fetch_all_activities(days_back=7)

    print("\n=== Commits ===")
    for c in activities["commits"][:3]:
        print(f"  [{c['sha']}] {c['message'][:50]}...")

    print("\n=== Pull Requests ===")
    for pr in activities["pull_requests"][:3]:
        print(f"  #{pr['number']} {pr['title']}")

    print("\n=== Issues ===")
    for issue in activities["issues"][:3]:
        print(f"  #{issue['number']} {issue['title']}")

    print("\n=== Discussions ===")
    for disc in activities["discussions"][:3]:
        print(f"  #{disc['number']} {disc['title']}")
