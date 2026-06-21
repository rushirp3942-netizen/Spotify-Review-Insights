import requests
import time
import sys
import os

# Add root folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_scrape_progress():
    url = "http://127.0.0.1:8000/api/scrape"
    payload = {
        "source": "play_store",
        "limit": 50, # Smaller limit for quick verification
        "query": "music discovery"
    }
    
    print("[Test] Launching background paginated scrape job for 50 reviews...")
    try:
        res = requests.post(url, json=payload, timeout=5)
        print(f"  - POST /api/scrape: Status {res.status_code}")
        if res.status_code != 200:
            print("  [ERROR] Failed to launch scrape task.")
            return False
            
        data = res.json()
        job_id = data.get("job_id")
        print(f"  - Scraping Job ID generated: {job_id}")
        
        status_url = f"http://127.0.0.1:8000/api/scrape/status/{job_id}"
        
        print("  - Starting status polling...")
        start_time = time.time()
        while True:
            status_res = requests.get(status_url, timeout=5)
            if status_res.status_code != 200:
                print(f"  [ERROR] Status check failed with code {status_res.status_code}")
                return False
                
            job_status = status_res.json()
            status = job_status.get("status")
            msg = job_status.get("message")
            current = job_status.get("current_count")
            
            print(f"    * [Job Status: {status}] Progress: {current}/50 reviews. Message: {msg}")
            
            if status == "completed":
                print(f"SUCCESS: Scraping completed in {time.time() - start_time:.1f} seconds!")
                print(f"Ingested {job_status.get('unique_added')} unique new reviews.")
                break
            elif status == "failed":
                print(f"  [ERROR] Ingestion job reported failure: {msg}")
                return False
                
            time.sleep(1)
            
    except Exception as e:
        print(f"  [ERROR] Request failed: {str(e)}")
        return False
        
    return True

if __name__ == "__main__":
    ok = test_scrape_progress()
    if ok:
        print("=== Phase 1 Verification Passed ===")
        sys.exit(0)
    else:
        print("=== Phase 1 Verification Failed ===")
        sys.exit(1)
