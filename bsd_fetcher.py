import requests
from bs4 import BeautifulSoup
import re

BSD_BASE_URL = "https://bsd.neuroinf.jp"
RECENT_ITEMS_URL = f"{BSD_BASE_URL}/wiki/%E8%84%B3%E7%A7%91%E5%AD%A6%E8%BE%9E%E5%85%B8:%E6%9C%80%E8%BF%91%E5%AE%8C%E6%88%90%E3%81%97%E3%81%9F%E9%A0%85%E7%9B%AE"

def fetch_recent_items_list():
    """
    Fetches the list of recently completed items from the BSD wiki.
    Returns a list of dicts: {'title': str, 'url': str}
    """
    try:
        response = requests.get(RECENT_ITEMS_URL, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching BSD recent items: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    
    # The structure is likely a list (ul/ol) inside the main content.
    # We'll look for the main content area first to avoid nav links.
    # MW (MediaWiki) usually puts content in #bodyContent or #mw-content-text
    content_div = soup.find('div', {'id': 'mw-content-text'})
    if not content_div:
        content_div = soup.find('div', {'class': 'mw-parser-output'})
    
    if not content_div:
        print("Could not find content div")
        return []

    items = []
    # Find all lists
    # The page "Recently Completed Items" likely contains a list of links.
    # We iterate through all links in the content area.
    # Filtering strategies might be needed if there are garbage links.
    
    # Assuming the most recent are at the top or in a specific list.
    # Let's grab all links that look like wiki entries (not internal special pages)
    
    for link in content_div.find_all('a'):
        href = link.get('href')
        title = link.get_text().strip()
        
        if not href or not title:
            continue
            
        # Filter out common wiki meta links if possible
        if "Special:" in href or "action=" in href or "oldid=" in href:
            continue
        
        if href.startswith("/wiki/"):
            full_url = f"{BSD_BASE_URL}{href}"
            items.append({'title': title, 'url': full_url})
            
    # Remove duplicates while preserving order
    seen_urls = set()
    unique_items = []
    for item in items:
        if item['url'] not in seen_urls:
            unique_items.append(item)
            seen_urls.add(item['url'])
            
    return unique_items

def fetch_article_content(url):
    """
    Fetches the text content of a BSD article.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching article {url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Get title
    title_h1 = soup.find('h1', {'id': 'firstHeading'})
    title = title_h1.get_text().strip() if title_h1 else "Unknown Title"
    
    # Get content
    content_div = soup.find('div', {'class': 'mw-parser-output'})
    if not content_div:
        content_div = soup.find('div', {'id': 'mw-content-text'})

    if not content_div:
        return None

    # Clean up content
    # Remove references, see also, external links sections if desired, or keep them.
    # Usually we want the main text.
    
    # Strategy: Iterate over paragraphs and headers
    text_content = ""
    
    # Remove tables of contents, edit links, etc.
    for trash in content_div.find_all(['div', 'table'], {'id': 'toc'}):
        trash.decompose()
    for trash in content_div.find_all('span', {'class': 'mw-editsection'}):
        trash.decompose()
        
    # Extract text from p, h2, h3, ul, ol
    # We might want to keep the structure loosely
    
    for element in content_div.find_all(['p', 'h2', 'h3', 'ul', 'ol']):
        # Stop at "References" or "Bibliography" usually
        text = element.get_text().strip()
        if text in ["参考文献", "関連項目", "外部リンク", "References", "See also", "External links"]:
            break
            
        if element.name in ['h2', 'h3']:
            text_content += f"\n\n## {text}\n\n"
        elif element.name in ['ul', 'ol']:
            for li in element.find_all('li'):
                text_content += f"- {li.get_text().strip()}\n"
            text_content += "\n"
        else:
            text_content += f"{text}\n\n"
            
    return {
        'title': title,
        'content': text_content,
        'url': url
    }

if __name__ == "__main__":
    # Test
    print("Fetching recent items...")
    items = fetch_recent_items_list()
    print(f"Found {len(items)} items.")
    if items:
        print(f"Top item: {items[0]}")
        print("Fetching content for top item...")
        content = fetch_article_content(items[0]['url'])
        if content:
            print(f"Title: {content['title']}")
            print(f"Content Length: {len(content['content'])}")
            print(f"Snippet: {content['content'][:200]}...")
