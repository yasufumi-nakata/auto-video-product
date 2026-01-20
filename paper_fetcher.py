"""
論文取得モジュール - discord-botのllm_serviceから移植
arXivとScopusから論文を取得
"""
import os
import requests
import feedparser
import urllib.parse
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

ELSEVIER_API_KEY = os.getenv("ELSEVIER_API_KEY")
SEARCH_QUERY = os.getenv("PAPER_SEARCH_QUERY", 'EEG OR "brain waves" OR "brain-computer interface"')


def fetch_arxiv(query, max_results=10, days_back=1):
    """arXivから論文を取得

    Args:
        query: 検索クエリ
        max_results: 最大取得件数
        days_back: 何日前までの論文を取得するか（1=前日のみ）
    """
    base_url = 'http://export.arxiv.org/api/query?'
    search_query = f'all:{query}'
    url = f'{base_url}search_query={urllib.parse.quote(search_query)}&sortBy=submittedDate&sortOrder=descending&max_results={max_results * 3}'  # 多めに取得してフィルタ

    feed = feedparser.parse(url)
    papers = []

    # 前日の日付範囲を計算
    target_date = (datetime.now() - timedelta(days=days_back)).date()
    cutoff_date = (datetime.now() - timedelta(days=days_back + 7)).date()  # 安全マージン

    for entry in feed.entries:
        pub_date = datetime.strptime(entry.published, '%Y-%m-%dT%H:%M:%SZ')

        # days_back=1の場合、前日以降の論文のみを取得
        if days_back > 0 and pub_date.date() < cutoff_date:
            continue

        doi = entry.get('arxiv_doi', '')
        authors = [a.name for a in entry.get('authors', [])]

        papers.append({
            'source': 'arXiv',
            'id': entry.id,
            'title': entry.title.replace('\n', ' '),
            'summary': entry.summary.replace('\n', ' '),
            'url': entry.link,
            'doi': doi,
            'authors': ", ".join(authors),
            'published': entry.published,
            'pub_date_obj': pub_date
        })

        if len(papers) >= max_results:
            break

    return papers


def get_crossref_abstract(doi):
    """CrossRef APIからアブストラクトを取得"""
    if not doi:
        return None
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": "BrainWavePaperBot/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            abstract = data.get('message', {}).get('abstract')
            if abstract:
                abstract = re.sub(r'<[^>]+>', '', abstract)
                return abstract.strip()
    except Exception as e:
        print(f"CrossRef error for DOI {doi}: {e}")
    return None


def fetch_elsevier(query, count=10, days_back=1):
    """Elsevier Scopusから論文を取得

    Args:
        query: 検索クエリ
        count: 最大取得件数
        days_back: 何日前までの論文を取得するか
    """
    if not ELSEVIER_API_KEY:
        print("Warning: ELSEVIER_API_KEY not set")
        return []

    # days_back日前からの論文を取得
    target_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": ELSEVIER_API_KEY,
        "Accept": "application/json"
    }
    params = {
        "query": f"TITLE-ABS-KEY({query}) AND LOAD-DATE AFT {target_date}",
        "count": min(count, 25),
        "sort": "-coverDate",
        "view": "STANDARD"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Elsevier API Error: {response.status_code}")
            return []

        data = response.json()
        entries = data.get('search-results', {}).get('entry', [])
        papers = []

        for entry in entries:
            pub_date_str = entry.get('prism:coverDate', '')
            try:
                pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d')
            except:
                pub_date = datetime.min

            doi = entry.get('prism:doi', '')
            summary = entry.get('dc:description')

            if not summary and doi:
                summary = get_crossref_abstract(doi)

            if not summary:
                summary = "アブストラクトなし"

            links = entry.get('link', [])
            paper_url = next((l.get('@href') for l in links if l.get('@ref') == 'scopus'), "")

            # DOIがある場合はDOI URLを使用
            if doi:
                paper_url = f"https://doi.org/{doi}"

            papers.append({
                'source': 'Scopus',
                'id': entry.get('dc:identifier', entry.get('eid')),
                'title': entry.get('dc:title', 'No Title').replace('\n', ' '),
                'summary': summary,
                'url': paper_url,
                'doi': doi,
                'authors': entry.get('dc:creator', 'Unknown'),
                'published': pub_date_str,
                'pub_date_obj': pub_date
            })
        return papers
    except Exception as e:
        print(f"Error fetching Elsevier: {e}")
        return []


def fetch_papers(query=None, max_results=5, days_back=1):
    """
    arXivとScopusから論文を取得してマージ

    Args:
        query: 検索クエリ（Noneの場合は環境変数から取得）
        max_results: 各ソースからの最大取得件数
        days_back: 何日前までの論文を取得するか（1=前日のみ）
    """
    if query is None:
        query = SEARCH_QUERY

    print(f"Fetching papers for: {query} (days_back={days_back})")

    papers = []

    # arXivから取得
    arxiv_papers = fetch_arxiv(query, max_results=max_results, days_back=days_back)
    print(f"arXiv: {len(arxiv_papers)} papers")
    papers.extend(arxiv_papers)

    # Scopusから取得
    scopus_papers = fetch_elsevier(query, count=max_results, days_back=days_back)
    print(f"Scopus: {len(scopus_papers)} papers")
    papers.extend(scopus_papers)

    # 日付でソート（新しい順）
    papers.sort(key=lambda x: x['pub_date_obj'], reverse=True)

    return papers


if __name__ == "__main__":
    papers = fetch_papers(max_results=3)
    for i, p in enumerate(papers):
        print(f"\n[{i+1}] {p['title']}")
        print(f"    Source: {p['source']}, URL: {p['url']}")
