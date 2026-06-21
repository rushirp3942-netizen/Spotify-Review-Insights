import os
import json
import hashlib
import urllib.parse
import time
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# Lazy load langdetect for robustness
try:
    from langdetect import detect
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False

def get_hash_id(content_str):
    """Generates a unique deterministic ID for a review based on its content."""
    return hashlib.md5(content_str.encode("utf-8", errors="ignore")).hexdigest()

def is_english(text):
    """Detects if the text content is in English."""
    if not HAS_LANGDETECT:
        return True
    try:
        # Clean URLs and punctuation for language detection
        cleaned = re.sub(r'http\S+|[^\w\s]', ' ', text).strip()
        # Remove consecutive spaces and numbers
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r'\d+', '', cleaned).strip()
        
        if len(cleaned) < 5:
            # If too short to detect accurately, assume English
            return True
            
        return detect(cleaned) == 'en'
    except Exception:
        return True # Default fallback to True if check fails

def is_valid_review(text):
    """Checks if a review is English and has at least 5 words."""
    if not text:
        return False
    words = text.split()
    if len(words) < 5:
        return False
    return is_english(text)

def scrape_play_store(app_id="com.spotify.music", limit=50, progress_callback=None):
    """Scrapes reviews from Google Play Store for Spotify, paginating and applying filters."""
    try:
        from google_play_scraper import Sort, reviews
    except ImportError:
        print("[Scraper] google-play-scraper library not found.")
        return []

    print(f"[Scraper] Ingesting up to {limit} valid English reviews from Google Play Store...")
    parsed_reviews = []
    continuation_token = None
    
    # We fetch in batches, but keep requesting more if items get filtered out
    while len(parsed_reviews) < limit:
        try:
            remaining = limit - len(parsed_reviews)
            # Fetch slightly more than needed in case some get filtered
            count_to_fetch = min(200, max(50, remaining * 2))
            
            if continuation_token is None:
                results, continuation_token = reviews(
                    app_id,
                    lang="en",
                    country="us",
                    sort=Sort.NEWEST,
                    count=count_to_fetch
                )
            else:
                results, continuation_token = reviews(
                    app_id,
                    continuation_token=continuation_token
                )
                
            if not results:
                print("[Scraper] Play Store: No more reviews returned.")
                break
                
            added_this_batch = 0
            for r in results:
                if len(parsed_reviews) >= limit:
                    break
                content = r.get("content", "").strip()
                
                # Apply word count and language filters
                if not is_valid_review(content):
                    continue
                    
                review_id = f"ps_{r.get('reviewId', get_hash_id(content))}"
                timestamp = r.get("at")
                iso_timestamp = timestamp.isoformat() if timestamp else datetime.utcnow().isoformat() + "Z"
                
                parsed_reviews.append({
                    "id": review_id,
                    "source": "play_store",
                    "content": content,
                    "rating": r.get("score"),
                    "author": r.get("userName", "Anonymous"),
                    "timestamp": iso_timestamp,
                    "url": f"https://play.google.com/store/apps/details?id={app_id}&reviewId={r.get('reviewId')}",
                    "analysis_status": "pending",
                    "analysis": None
                })
                added_this_batch += 1
                
            print(f"[Scraper] Play Store: fetched {len(parsed_reviews)} / {limit} valid reviews.")
            if progress_callback:
                progress_callback(len(parsed_reviews), len(parsed_reviews))
                
            if not continuation_token:
                print("[Scraper] Play Store: End of reviews reached.")
                break
                
            time.sleep(0.5)
            
        except Exception as e:
            print(f"[Scraper] Error in Play Store scrape loop: {str(e)}")
            break
            
    return parsed_reviews

def scrape_reddit(query="music discovery", limit=50, progress_callback=None):
    """Fetches public JSON feed from Reddit search for r/spotify, paginating and filtering."""
    print(f"[Scraper] Ingesting up to {limit} valid English posts from Reddit search for: '{query}'...")
    parsed_reviews = []
    after = None
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    while len(parsed_reviews) < limit:
        remaining = limit - len(parsed_reviews)
        batch_limit = min(100, max(25, remaining * 2))
        
        encoded_query = urllib.parse.quote(f"{query} OR recommendation OR shuffle OR discovery")
        url = f"https://www.reddit.com/r/spotify/search.json?q={encoded_query}&restrict_sr=1&sort=relevance&limit={batch_limit}"
        if after:
            url += f"&after={after}"
            
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"[Scraper] Reddit returned status code {response.status_code}")
                break
                
            data = response.json().get("data", {})
            posts = data.get("children", [])
            after = data.get("after")
            
            if not posts:
                print("[Scraper] Reddit: No more posts returned.")
                break
                
            for post in posts:
                if len(parsed_reviews) >= limit:
                    break
                pdata = post.get("data", {})
                title = pdata.get("title", "").strip()
                body = pdata.get("selftext", "").strip()
                
                # Combine title and body to get the full feedback text
                full_text = f"{title}\n{body}".strip() if body else title
                
                # Apply word count and language filters
                if not is_valid_review(full_text):
                    continue
                    
                post_id = f"rd_{pdata.get('id', get_hash_id(full_text))}"
                created_utc = pdata.get("created_utc")
                iso_timestamp = datetime.utcfromtimestamp(created_utc).isoformat() + "Z" if created_utc else datetime.utcnow().isoformat() + "Z"
                
                parsed_reviews.append({
                    "id": post_id,
                    "source": "reddit",
                    "content": full_text,
                    "rating": None,
                    "author": f"u/{pdata.get('author', 'anonymous')}",
                    "timestamp": iso_timestamp,
                    "url": f"https://reddit.com{pdata.get('permalink')}",
                    "analysis_status": "pending",
                    "analysis": None
                })
                
            print(f"[Scraper] Reddit: fetched {len(parsed_reviews)} / {limit} valid reviews.")
            if progress_callback:
                progress_callback(len(parsed_reviews), len(parsed_reviews))
                
            if not after:
                print("[Scraper] Reddit: End of search results.")
                break
                
            time.sleep(0.5)
            
        except Exception as e:
            print(f"[Scraper] Error in Reddit scrape loop: {str(e)}")
            break
            
    return parsed_reviews

def scrape_spotify_community(query="music discovery", limit=10, progress_callback=None):
    """Scrapes Spotify Community search page using BeautifulSoup, paginating and filtering."""
    print(f"[Scraper] Ingesting up to {limit} valid English posts from Spotify Forums for: '{query}'...")
    parsed_reviews = []
    page = 1
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    while len(parsed_reviews) < limit:
        encoded_query = urllib.parse.quote(query)
        url = f"https://community.spotify.com/t5/forums/searchpage/tab/message?q={encoded_query}&page={page}"
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"[Scraper] Spotify Community returned status code {response.status_code}")
                break
                
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.find_all("div", class_="lia-message-card") or soup.find_all("tr", class_="lia-list-row")
            
            if not items:
                print(f"[Scraper] Spotify Forums: No results found on page {page}.")
                break
                
            added_on_page = 0
            for i, item in enumerate(items):
                if len(parsed_reviews) >= limit:
                    break
                title_el = item.find("a", class_="lia-link-navigation") or item.find("h2")
                snippet_el = item.find("div", class_="lia-message-body") or item.find("p")
                author_el = item.find("a", class_="lia-user-name_link")
                
                title = title_el.text.strip() if title_el else ""
                body = snippet_el.text.strip() if snippet_el else ""
                
                # Combine thread title and body snippet
                full_text = f"{title}\n{body}".strip() if body else title
                
                # Apply word count and language filters
                if not is_valid_review(full_text):
                    continue
                    
                author = author_el.text.strip() if author_el else "forum_user"
                link = title_el["href"] if title_el and title_el.has_attr("href") else "https://community.spotify.com"
                if not link.startswith("http"):
                    link = "https://community.spotify.com" + link
                    
                post_id = f"sf_{get_hash_id(full_text)[:12]}"
                
                parsed_reviews.append({
                    "id": post_id,
                    "source": "spotify_forum",
                    "content": full_text,
                    "rating": None,
                    "author": author,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "url": link,
                    "analysis_status": "pending",
                    "analysis": None
                })
                added_on_page += 1
                
            print(f"[Scraper] Spotify Forums: fetched {len(parsed_reviews)} / {limit} valid reviews (Page {page}).")
            if progress_callback:
                progress_callback(len(parsed_reviews), len(parsed_reviews))
                
            if added_on_page == 0:
                break
                
            page += 1
            time.sleep(0.5)
            
        except Exception as e:
            print(f"[Scraper] Error in Spotify Community scrape loop: {str(e)}")
            break
            
    return parsed_reviews

def load_mock_data():
    """Loads pre-packaged mock reviews database, cleaning up elements to match schema."""
    print("[Scraper] Loading pre-packaged mock dataset...")
    mock_file = os.path.join(os.path.dirname(__file__), "mock_data.json")
    if os.path.exists(mock_file):
        try:
            with open(mock_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                cleaned_data = []
                for item in raw_data:
                    # Filter out short reviews
                    content = item.get("content", "")
                    if len(content.split()) < 5:
                        continue
                    
                    # Construct matching schema without title
                    cleaned_item = {
                        "id": item.get("id"),
                        "source": item.get("source"),
                        "content": content,
                        "rating": item.get("rating"),
                        "author": item.get("author"),
                        "timestamp": item.get("timestamp"),
                        "url": item.get("url"),
                        "analysis_status": item.get("analysis_status"),
                        "analysis": item.get("analysis")
                    }
                    cleaned_data.append(cleaned_item)
                return cleaned_data
        except Exception as e:
            print(f"[Scraper] Error reading mock_data.json: {str(e)}")
    return []
