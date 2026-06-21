import os
import json
import re
from datetime import datetime

def get_groq_client(api_key):
    try:
        from groq import Groq
        import httpx
        return Groq(
            api_key=api_key,
            http_client=httpx.Client(
                http2=False,
                timeout=60.0
            )
        )
    except ImportError:
        raise Exception("The 'groq' package is not installed. Please verify installation status.")

def analyze_review(api_key, model_id, review_text, source="play_store", rating=None):
    """Sends a single review to Groq to extract structured analysis fields (no title)."""
    if not api_key:
        raise Exception("Groq API Key is not configured.")
        
    client = get_groq_client(api_key)
    rating_str = f" [Rating: {rating}/5]" if rating is not None else ""
    
    prompt = f"""You are a senior Spotify Growth Product Researcher analyzing user feedback.
Analyze this review:
---
Source: {source}{rating_str}
Content: {review_text}
---

Perform the following classification and return ONLY a valid JSON object containing these keys:
1. "sentiment": One of "Positive", "Neutral", "Negative".
2. "category": Choose the single most fitting category from: "Algorithm Frustration", "Playlist Management", "UI/UX", "Repeat Listening", "Music Discovery", "Other".
3. "summary": A concise one-sentence summary of the review (max 15 words).
4. "pain_point": A short phrase (2-5 words) identifying the primary frustration or need (e.g., "Shuffle repeating songs", "Familiar artist loop", "Exhausting discovery effort").
5. "discovery_issue": A boolean (true or false) indicating if the user is struggling to find or listen to new, unfamiliar music.

Your response must be a single JSON object. Do not wrap in markdown ```json or include any text before/after.
JSON format example:
{{
  "sentiment": "Negative",
  "category": "Music Discovery",
  "summary": "User finds the recommendations too repetitive.",
  "pain_point": "Repetitive recommendations",
  "discovery_issue": true
}}"""

    messages = [
        {"role": "system", "content": "You are a precise classifier that outputs only valid JSON."},
        {"role": "user", "content": prompt}
    ]

    try:
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
        except Exception as json_err:
            print(f"[Analyzer] JSON Mode failed, falling back to standard completion: {str(json_err)}")
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()

        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)
            
        analysis_data = json.loads(content)
        
        validated = {
            "sentiment": str(analysis_data.get("sentiment", "Neutral")),
            "category": str(analysis_data.get("category", "Other")),
            "summary": str(analysis_data.get("summary", "No summary.")),
            "pain_point": str(analysis_data.get("pain_point", "N/A")),
            "discovery_issue": bool(analysis_data.get("discovery_issue", False)),
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            "model_used": model_id
        }
        return validated
        
    except Exception as e:
        print(f"[Analyzer] Error during Groq API call: {str(e)}")
        return {
            "sentiment": "Neutral",
            "category": "Other",
            "summary": "Analysis failed.",
            "pain_point": "Error performing analysis",
            "discovery_issue": False,
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            "model_used": model_id,
            "error": str(e)
        }

def synthesize_key_questions(api_key, model_id, reviews, question_id):
    """Answers specific product research questions based on the review corpus (no title)."""
    if not api_key:
        raise Exception("Groq API Key is not configured.")
        
    client = get_groq_client(api_key)
    
    questions_map = {
        "q1": "Why do users struggle to discover new music?",
        "q2": "What are the most common frustrations with Spotify's recommendation system?",
        "q3": "What listening goals or behaviors are users trying to achieve?",
        "q4": "Why do users repeatedly listen to the same playlists, artists, or songs?",
        "q5": "Which user segments face different music discovery challenges?",
        "q6": "What unmet needs consistently emerge across user feedback?",
        "q7": "What product improvement opportunities can be identified from the collected data?"
    }
    
    question = questions_map.get(question_id, question_id)
    relevant_reviews = [r for r in reviews if r.get("analysis_status") == "analyzed"]
    
    if question_id == "q4":
        relevant_reviews.sort(key=lambda x: 0 if (x.get("analysis") or {}).get("category") == "Repeat Listening" else 1)
    elif question_id == "q1" or question_id == "q6":
        relevant_reviews.sort(key=lambda x: 0 if (x.get("analysis") or {}).get("discovery_issue") else 1)
    elif question_id == "q2":
        relevant_reviews.sort(key=lambda x: 0 if (x.get("analysis") or {}).get("category") == "Algorithm Frustration" else 1)
        
    sample_context = ""
    for r in relevant_reviews[:30]:
        analysis = r.get("analysis") or {}
        sample_context += f"- [{r['source'].upper()} Rating: {r.get('rating') or 'N/A'}] Pain Point: {analysis.get('pain_point', 'N/A')}\n  Review: {r['content'][:200]}\n"
        
    if not sample_context:
        sample_context = "No analyzed reviews are available. Please seed mock data or scrape reviews."

    prompt = f"""You are the Lead Growth Product Researcher at Spotify. You have been asked to answer the following research question using a synthesized dataset of user feedback:
Question: "{question}"

Below is a compiled summary of user feedback and pain points gathered from Google Play, Reddit, and Spotify Community Forums:
---
{sample_context}
---

Based on the feedback above, synthesize a professional, structured answer. Use markdown with headings, bullets, and bold text. Make sure to:
1. Directly answer the question with specific patterns found in the feedback.
2. Outline 2-3 specific user quotes or typical behaviors described.
3. Suggest 1-2 product suggestions that directly address the findings.
Provide a clean, actionable output for the Spotify Growth Product Team.
"""

    messages = [
        {"role": "system", "content": "You are a helpful, senior Spotify Product Analyst. Provide professional, structured markdown responses."},
        {"role": "user", "content": prompt}
    ]
    
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Analyzer] Question synthesis failed: {str(e)}")
        return f"Error synthesizing answer: {str(e)}"

def generate_one_page_summary(api_key, model_id, reviews):
    """Generates an HTML One-Page growth summary report based on aggregated metrics and reviews (no title)."""
    if not api_key:
        raise Exception("Groq API Key is not configured.")
        
    client = get_groq_client(api_key)
    
    total = len(reviews)
    analyzed = [r for r in reviews if r.get("analysis_status") == "analyzed"]
    analyzed_count = len(analyzed)
    
    if analyzed_count == 0:
        return "<h3>No analyzed reviews available. Please run LLM analysis or seed sample reviews.</h3>"
        
    discovery_count = sum(1 for r in analyzed if (r.get("analysis") or {}).get("discovery_issue") is True)
    discovery_ratio = (discovery_count / analyzed_count) * 100 if analyzed_count > 0 else 0
    
    pos = sum(1 for r in analyzed if (r.get("analysis") or {}).get("sentiment") == "Positive")
    neu = sum(1 for r in analyzed if (r.get("analysis") or {}).get("sentiment") == "Neutral")
    neg = sum(1 for r in analyzed if (r.get("analysis") or {}).get("sentiment") == "Negative")
    
    pos_pct = int((pos / analyzed_count) * 100) if analyzed_count > 0 else 0
    neu_pct = int((neu / analyzed_count) * 100) if analyzed_count > 0 else 0
    neg_pct = int((neg / analyzed_count) * 100) if analyzed_count > 0 else 0
    
    categories_freq = {}
    pain_points_freq = {}
    feedback_samples = []
    
    for r in analyzed:
        analysis = r.get("analysis") or {}
        cat = analysis.get("category", "Other")
        pain = analysis.get("pain_point", "N/A")
        categories_freq[cat] = categories_freq.get(cat, 0) + 1
        pain_points_freq[pain] = pain_points_freq.get(pain, 0) + 1
        
        if len(feedback_samples) < 25:
            source_str = (r.get("source") or "unknown").upper()
            content_str = r.get("content") or ""
            feedback_samples.append(f"- [{source_str}] Category: {cat} | Pain: {pain}\n  \"{content_str[:150]}...\"")
            
    feedback_context = "\n\n".join(feedback_samples)
    
    prompt = f"""You are the Lead Growth Product Researcher at Spotify. Prepare a high-impact, one-page Executive Growth Report based on the following aggregated user feedback:

[Aggregated Metrics]:
- Total reviews analyzed: {analyzed_count}
- Discovery pain point ratio: {discovery_ratio:.1f}% (percentage of users experiencing discovery challenges)
- Sentiment breakdown: Positive ({pos_pct}%), Neutral ({neu_pct}%), Negative ({neg_pct}%)

[User Feedback Context]:
{feedback_context}

Format your response in structured, beautiful HTML with inline CSS. Use a Spotify-themed design: dark backgrounds (#121212), white text, and spotify green (#1DB954) accents. The report must contain:
1. A top header titled "Spotify Music Discovery - Growth Product Report".
2. "Executive Summary": A paragraph highlighting the core findings and the friction around discovery vs familiar repeat listening.
3. "Top 3 Discovery Barriers": Clear definitions of the 3 primary friction points users experience when discovering music (e.g. recommendation loops, Smart Shuffle issues).
4. "Key User Persona": A brief profile of the user segment facing the most discovery challenges (e.g. 'The Trapped Enthusiast').
5. "Growth Recommendations": 3 actionable feature proposals or improvements for the Spotify Growth Product Team.

Return only the HTML body content inside a container div. Do not include markdown wraps (like ```html).
Make it visually stunning, using colors: #1DB954 (Spotify Green), #191414 (Spotify Black), #181818 (Card background), #B3B3B3 (Gray text), and #FFFFFF (White text). Use inline CSS padding, borders, margins, and border-radius (e.g., 8px) to make cards stand out. Ensure all styles are inline.
"""

    messages = [
        {"role": "system", "content": "You are a professional designer and product analyst who outputs inline-styled HTML summaries only."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=0.3
        )
        html_report = response.choices[0].message.content.strip()
        
        if html_report.startswith("```html"):
            html_report = html_report.replace("```html", "", 1)
        if html_report.startswith("```"):
            html_report = html_report.replace("```", "", 1)
        if html_report.endswith("```"):
            html_report = html_report[:-3]
            
        return html_report.strip()
    except Exception as e:
        print(f"[Analyzer] Failed to generate HTML report: {str(e)}")
        return f"<h3>Error generating report: {str(e)}</h3>"
