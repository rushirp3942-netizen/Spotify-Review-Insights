import os
import json
import uuid
import time
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv

# Load environment variables from .env file at startup
load_dotenv()

# Import from package namespaces
from phase1_data_collection import scraper
from phase2_analysis_and_report import analyzer, email_service

app = FastAPI(title="Spotify Review Analysis System API")

# File paths
DB_FILE = os.environ.get("REVIEWS_DB_PATH", "reviews_db.json")
CONFIG_FILE = "config.json"
STATIC_DIR = "static"

# Ensure static directory exists
os.makedirs(STATIC_DIR, exist_ok=True)

# Global dictionaries to track background jobs
scrape_jobs = {}
analysis_jobs = {}

# Helper functions for database management
def load_db() -> list:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[API] Error loading database: {str(e)}")
    # Default to seeding with mock data if DB doesn't exist
    mock_data = scraper.load_mock_data()
    if mock_data:
        save_db(mock_data)
        return mock_data
    return []

def save_db(data: list):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[API] Error saving database: {str(e)}")

# Helper functions for config management
def load_config() -> dict:
    default_config = {
        "groq_api_key": os.environ.get("GROQ_API_KEY", "").strip(),
        "groq_model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        "smtp_host": os.environ.get("SMTP_HOST", "").strip(),
        "smtp_port": os.environ.get("SMTP_PORT", "587").strip(),
        "smtp_username": os.environ.get("SMTP_USERNAME", "").strip(),
        "smtp_password": os.environ.get("SMTP_PASSWORD", "").strip(),
        "smtp_sender_email": os.environ.get("SMTP_SENDER_EMAIL", "").strip()
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                # Clean up any string values by stripping trailing newlines/spaces
                cleaned = {k: v.strip() if isinstance(v, str) else v for k, v in saved.items()}
                # Update default config, but do not overwrite non-empty environment variables with empty values
                for k, v in cleaned.items():
                    if v or not default_config.get(k):
                        default_config[k] = v
        except Exception as e:
            print(f"[API] Error loading configuration: {str(e)}")
    return default_config

def save_config(config: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[API] Error saving configuration: {str(e)}")

# Pydantic schemas
class GroqConfigUpdate(BaseModel):
    groq_api_key: str
    groq_model: str

class SMTPConfigUpdate(BaseModel):
    host: str
    port: str
    username: str
    password: str
    sender_email: str

class ScrapeRequest(BaseModel):
    source: str # play_store, reddit, spotify_forum
    limit: int = 20
    query: str = "music discovery"

class EmailRequest(BaseModel):
    recipient_email: str
    subject: str
    personalized_note: str = ""

class QueryRequest(BaseModel):
    question_id: str # q1 - q7, or custom
    custom_query: Optional[str] = None

# Background Scraper Worker Thread
def run_scraper_task(job_id: str, source: str, limit: int, query: str):
    job = scrape_jobs.get(job_id)
    if not job:
        return
        
    job["status"] = "running"
    job["message"] = "Initializing pagination request loops..."
    
    def progress_callback(current, total):
        job["current_count"] = current
        job["message"] = f"Downloaded {current} / {limit} entries..."
        
    try:
        new_reviews = []
        if source == "play_store":
            new_reviews = scraper.scrape_play_store(limit=limit, progress_callback=progress_callback)
        elif source == "reddit":
            new_reviews = scraper.scrape_reddit(query=query, limit=limit, progress_callback=progress_callback)
        elif source == "spotify_forum":
            new_reviews = scraper.scrape_spotify_community(query=query, limit=limit, progress_callback=progress_callback)
        else:
            raise Exception("Invalid platform source.")
            
        if not new_reviews:
            job["status"] = "completed"
            job["message"] = "Completed. Scraper fetched 0 reviews."
            return
            
        # Ingest into database
        db = load_db()
        existing_ids = {r["id"] for r in db}
        
        added_count = 0
        for r in new_reviews:
            if r["id"] not in existing_ids:
                db.insert(0, r)
                existing_ids.add(r["id"])
                added_count += 1
                
        if added_count > 0:
            save_db(db)
            
        job["status"] = "completed"
        job["unique_added"] = added_count
        job["current_count"] = len(new_reviews)
        job["message"] = f"Completed successfully! Crawled {len(new_reviews)} reviews. Ingested {added_count} new unique records."
        
    except Exception as e:
        job["status"] = "failed"
        job["message"] = f"Ingestion failed: {str(e)}"

# Background Analysis Worker Thread
def run_analysis_task(job_id: str, api_key: str, model_id: str):
    job = analysis_jobs.get(job_id)
    if not job:
        return
        
    job["status"] = "running"
    job["message"] = "Reading review records from database..."
    
    try:
        # Load DB and check pending reviews
        db = load_db()
        pending = [r for r in db if r["analysis_status"] == "pending"]
        total_pending = len(pending)
        
        job["total_pending"] = total_pending
        
        if total_pending == 0:
            job["status"] = "completed"
            job["message"] = "Finished. No pending reviews left to classify."
            return
            
        for idx, r in enumerate(pending):
            job["message"] = f"Analyzing review {idx + 1} of {total_pending} via Groq..."
            
            # Perform LLM request
            analysis = analyzer.analyze_review(
                api_key=api_key,
                model_id=model_id,
                review_text=r["content"],
                source=r["source"],
                rating=r.get("rating")
            )
            
            # Update review record in-memory
            r["analysis"] = analysis
            r["analysis_status"] = "analyzed" if "error" not in analysis else "failed"
            
            # Progressive database commit: save after every classified review
            # to preserve progress in case of rate limits or server restarts.
            save_db(db)
            
            # Update job state
            job["current_count"] = idx + 1
            job["message"] = f"Analyzed {idx + 1} / {total_pending} reviews..."
            
            # Rate limit mitigation pause
            time.sleep(0.2)
            
        job["status"] = "completed"
        job["message"] = f"Successfully classified all {total_pending} pending reviews!"
        
    except Exception as e:
        job["status"] = "failed"
        job["message"] = f"Bulk classification failed: {str(e)}"

# API Endpoints

@app.get("/api/config")
def get_config():
    cfg = load_config()
    masked_key = ""
    if cfg["groq_api_key"]:
        masked_key = cfg["groq_api_key"][:6] + "..." + cfg["groq_api_key"][-4:] if len(cfg["groq_api_key"]) > 10 else "Configured"
        
    return {
        "groq_api_key_configured": bool(cfg["groq_api_key"]),
        "groq_api_key_preview": masked_key,
        "groq_model": cfg["groq_model"]
    }

@app.post("/api/config")
def update_config(data: GroqConfigUpdate):
    cfg = load_config()
    cfg["groq_api_key"] = data.groq_api_key.strip()
    cfg["groq_model"] = data.groq_model.strip()
    save_config(cfg)
    return {"status": "success", "message": "Groq configuration updated."}

@app.get("/api/config/smtp")
def get_smtp_config():
    cfg = load_config()
    return {
        "host": cfg["smtp_host"],
        "port": cfg["smtp_port"],
        "username": cfg["smtp_username"],
        "sender_email": cfg["smtp_sender_email"],
        "password_configured": bool(cfg["smtp_password"])
    }

@app.post("/api/config/smtp")
def update_smtp_config(data: SMTPConfigUpdate):
    cfg = load_config()
    cfg["smtp_host"] = data.host.strip()
    cfg["smtp_port"] = data.port.strip()
    cfg["smtp_username"] = data.username.strip()
    # Keep existing password if the incoming one is empty
    new_password = data.password.strip()
    if new_password:
        cfg["smtp_password"] = new_password
    cfg["smtp_sender_email"] = data.sender_email.strip()
    save_config(cfg)
    return {"status": "success", "message": "SMTP configuration updated."}

@app.post("/api/scrape")
def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    scrape_jobs[job_id] = {
        "status": "pending",
        "source": req.source,
        "limit": req.limit,
        "current_count": 0,
        "unique_added": 0,
        "message": "Scrape task queued..."
    }
    
    background_tasks.add_task(run_scraper_task, job_id, req.source, req.limit, req.query)
    
    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "Scrape task initiated in background."
    }

@app.get("/api/scrape/status/{job_id}")
def get_scrape_status(job_id: str):
    job = scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scraping job not found.")
    return job

@app.get("/api/reviews")
def get_reviews(
    source: Optional[str] = None,
    sentiment: Optional[str] = None,
    category: Optional[str] = None,
    discovery_issue: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    db = load_db()
    filtered = db
    
    if source:
        filtered = [r for r in filtered if r["source"] == source]
    if sentiment:
        filtered = [r for r in filtered if (r.get("analysis") or {}).get("sentiment") == sentiment]
    if category:
        filtered = [r for r in filtered if (r.get("analysis") or {}).get("category") == category]
    if discovery_issue is not None:
        filtered = [r for r in filtered if (r.get("analysis") or {}).get("discovery_issue") == discovery_issue]
    if search:
        search_lower = search.lower()
        filtered = [
            r for r in filtered 
            if search_lower in r["content"].lower()
        ]
        
    total_matches = len(filtered)
    paginated = filtered[offset : offset + limit]
    
    return {
        "total": total_matches,
        "count": len(paginated),
        "reviews": paginated
    }

@app.get("/api/reviews/stats")
def get_reviews_stats():
    db = load_db()
    total = len(db)
    analyzed = [r for r in db if r["analysis_status"] == "analyzed"]
    analyzed_count = len(analyzed)
    pending_count = sum(1 for r in db if r["analysis_status"] == "pending")
    
    sentiments = {"Positive": 0, "Neutral": 0, "Negative": 0}
    categories = {}
    pain_points = {}
    discovery_issues_count = 0
    
    for r in analyzed:
        analysis = r.get("analysis") or {}
        sent = analysis.get("sentiment", "Neutral")
        sentiments[sent] = sentiments.get(sent, 0) + 1
        
        cat = analysis.get("category", "Other")
        categories[cat] = categories.get(cat, 0) + 1
        
        pain = analysis.get("pain_point", "N/A")
        if pain and pain != "N/A" and pain != "Error performing analysis":
            pain_points[pain] = pain_points.get(pain, 0) + 1
            
        if analysis.get("discovery_issue") is True:
            discovery_issues_count += 1
            
    sorted_pain_points = sorted(pain_points.items(), key=lambda x: x[1], reverse=True)[:5]
    top_pain_points = [{"pain_point": k, "count": v} for k, v in sorted_pain_points]
    
    play_store_ratings = [r["rating"] for r in db if r["source"] == "play_store" and r["rating"] is not None]
    avg_rating = round(sum(play_store_ratings) / len(play_store_ratings), 2) if play_store_ratings else None
    
    return {
        "total_count": total,
        "analyzed_count": analyzed_count,
        "pending_count": pending_count,
        "average_rating": avg_rating,
        "discovery_issues_count": discovery_issues_count,
        "discovery_ratio": round((discovery_issues_count / analyzed_count) * 100, 1) if analyzed_count > 0 else 0.0,
        "sentiments": sentiments,
        "categories": categories,
        "top_pain_points": top_pain_points
    }

@app.post("/api/analyze")
def trigger_analysis(background_tasks: BackgroundTasks):
    cfg = load_config()
    api_key = cfg["groq_api_key"]
    model_id = cfg["groq_model"]
    
    if not api_key:
        raise HTTPException(status_code=400, detail="Groq API Key is not configured in settings.")
        
    db = load_db()
    pending = [r for r in db if r["analysis_status"] == "pending"]
    total_pending = len(pending)
    
    if total_pending == 0:
        return {"status": "no_work", "message": "No pending reviews left to classify."}
        
    # Queue the analysis task
    job_id = str(uuid.uuid4())
    analysis_jobs[job_id] = {
        "status": "pending",
        "total_pending": total_pending,
        "current_count": 0,
        "message": "Analysis job queued..."
    }
    
    background_tasks.add_task(run_analysis_task, job_id, api_key, model_id)
    
    return {
        "status": "accepted",
        "job_id": job_id,
        "total_pending": total_pending,
        "message": "Bulk analysis started in the background."
    }

@app.get("/api/analyze/status/{job_id}")
def get_analysis_status(job_id: str):
    job = analysis_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return job

@app.post("/api/query")
def query_corpus(req: QueryRequest):
    cfg = load_config()
    api_key = cfg["groq_api_key"]
    model_id = cfg["groq_model"]
    
    if not api_key:
        raise HTTPException(status_code=400, detail="Groq API Key is not configured in settings.")
        
    db = load_db()
    
    if req.question_id == "custom":
        if not req.custom_query:
            raise HTTPException(status_code=400, detail="Custom query text is required.")
        answer = analyzer.synthesize_key_questions(api_key, model_id, db, req.custom_query)
    else:
        answer = analyzer.synthesize_key_questions(api_key, model_id, db, req.question_id)
        
    return {"answer": answer}

@app.post("/api/report/generate-one-pager")
def generate_report():
    cfg = load_config()
    api_key = cfg["groq_api_key"]
    model_id = cfg["groq_model"]
    
    if not api_key:
        raise HTTPException(status_code=400, detail="Groq API Key is not configured in settings.")
        
    try:
        db = load_db()
        html_report = analyzer.generate_one_page_summary(api_key, model_id, db)
        
        try:
            with open("cached_report.html", "w", encoding="utf-8") as f:
                f.write(html_report)
        except Exception as e:
            print(f"[API] Error caching report: {str(e)}")
            
        return {"html_report": html_report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@app.post("/api/report/send-email")
def send_report_by_email(req: EmailRequest):
    cfg = load_config()
    smtp_config = {
        "host": cfg["smtp_host"],
        "port": cfg["smtp_port"],
        "username": cfg["smtp_username"],
        "password": cfg["smtp_password"],
        "sender_email": cfg["smtp_sender_email"]
    }
    
    report_html = ""
    if os.path.exists("cached_report.html"):
        try:
            with open("cached_report.html", "r", encoding="utf-8") as f:
                report_html = f.read()
        except Exception as e:
            print(f"[API] Error reading cached report: {str(e)}")
            
    if not report_html:
        if cfg["groq_api_key"]:
            db = load_db()
            report_html = analyzer.generate_one_page_summary(cfg["groq_api_key"], cfg["groq_model"], db)
        else:
            raise HTTPException(
                status_code=400, 
                detail="No cached report available and Groq is not configured."
            )
            
    try:
        result = email_service.send_html_email(
            smtp_config=smtp_config,
            recipient_email=req.recipient_email,
            subject=req.subject,
            html_content=report_html,
            personalized_note=req.personalized_note
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email delivery failed: {str(e)}")

@app.post("/api/mock-data")
def load_mock():
    mock_reviews = scraper.load_mock_data()
    if mock_reviews:
        save_db(mock_reviews)
        return {
            "status": "success",
            "count": len(mock_reviews),
            "message": "Reviews database reset and seeded with mock data."
        }
    else:
        raise HTTPException(status_code=500, detail="Mock data file could not be read.")

# Serve static dashboard files
@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to Spotify Review Analysis System! Front-end assets are not compiled yet."}

# Mount static files directory
app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
