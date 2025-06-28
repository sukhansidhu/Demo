import os

class Config:
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")
    TMP_DIR = "/tmp/archive_bot"
    
    # Create temp directory if not exists
    if not os.path.exists(TMP_DIR):
        os.makedirs(TMP_DIR)
