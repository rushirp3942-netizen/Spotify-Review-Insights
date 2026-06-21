import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

def send_html_email(smtp_config, recipient_email, subject, html_content, personalized_note=""):
    """
    Sends an HTML report to the recipient.
    smtp_config can contain: host, port, username, password, sender_email.
    If credentials are not complete, it falls back to simulation mode.
    """
    recipients = [r.strip() for r in recipient_email.split(",") if r.strip()]
    if not recipients:
        raise Exception("No valid recipient email address provided.")
        
    host = smtp_config.get("host")
    port = smtp_config.get("port")
    user = smtp_config.get("username")
    pwd = smtp_config.get("password")
    sender = smtp_config.get("sender_email") or user
    
    is_configured = all([host, port, user, pwd, sender])
    
    email_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #121212; padding: 20px; color: #FFFFFF;">
        {f'<div style="background-color: #181818; border-left: 4px solid #1DB954; padding: 15px; margin-bottom: 20px; border-radius: 4px;"><h4 style="margin: 0 0 5px 0; color: #1DB954;">Personalized Note:</h4><p style="margin: 0; color: #B3B3B3; font-style: italic;">"{personalized_note}"</p></div>' if personalized_note else ''}
        <div style="background-color: #121212; border-radius: 8px; overflow: hidden; border: 1px solid #282828;">
            {html_content}
        </div>
        <p style="color: #535353; font-size: 11px; text-align: center; margin-top: 20px;">
            This executive summary was generated using Groq LLM on Spotify Growth reviews database.
        </p>
    </body>
    </html>
    """

    if not is_configured:
        # Simulation Mode
        # Log to the parent directory (workspace root) so it's easy for the user to find
        log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sent_emails_log.txt")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = f"""==================================================
EMAIL TRANSMISSION SIMULATION LOG
Timestamp: {timestamp}
From: {sender or 'simulated-sender@spotify-growth.local'}
To: {', '.join(recipients)}
Subject: {subject}
Personalized Note: {personalized_note or '(None)'}
--------------------------------------------------
HTML CONTENT PREVIEW:
{email_html}
==================================================

"""
        try:
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(log_entry)
            print(f"[Email Service] [SIMULATION] Saved email to: {log_file_path}")
            return {
                "success": True,
                "simulation": True,
                "recipients": recipients,
                "log_file": log_file_path
            }
        except Exception as file_err:
            raise Exception(f"Failed to write to simulation log file: {str(file_err)}")
            
    # Real SMTP Mode
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        
        part_html = MIMEText(email_html, "html")
        msg.attach(part_html)
        
        port_int = int(port)
        if port_int == 465:
            server = smtplib.SMTP_SSL(host, port_int, timeout=10)
        else:
            server = smtplib.SMTP(host, port_int, timeout=10)
            server.starttls()
            
        server.login(user, pwd)
        server.sendmail(sender, recipients, msg.as_string())
        server.quit()
        
        print(f"[Email Service] Email sent successfully to {', '.join(recipients)}")
        return {
            "success": True,
            "simulation": False,
            "recipients": recipients
        }
    except Exception as smtp_err:
        print(f"[Email Service] Real SMTP transmission failed: {str(smtp_err)}")
        try:
            log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sent_emails_log.txt")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"!!! REAL SMTP ATTEMPT FAILED: {str(smtp_err)} !!!\n" + \
                        f"Timestamp: {timestamp}\nFrom: {sender}\nTo: {', '.join(recipients)}\nSubject: {subject}\n" + \
                        f"HTML CONTENT PREVIEW:\n{email_html}\n\n"
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(log_entry)
            return {
                "success": True,
                "simulation": True,
                "smtp_error": str(smtp_err),
                "recipients": recipients,
                "log_file": log_file_path
            }
        except Exception:
            raise smtp_err
