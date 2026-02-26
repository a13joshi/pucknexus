import json
from supabase_config import supabase

def migrate():
    # 1. Load your local JSON file
    try:
        with open('oauth2.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ Could not find oauth2.json. Make sure it's in the root folder.")
        return

    # 2. Prepare the data for Supabase
    auth_payload = {
        "id": "yahoo_token",
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "consumer_key": data.get("consumer_key"),
        "consumer_secret": data.get("consumer_secret"),
        "token_time": data.get("token_time")
    }

    # 3. Upsert to the database
    response = supabase.table("auth_vault").upsert(auth_payload).execute()
    
    if response:
        print("✅ Success! Your Yahoo tokens are now securely stored in Supabase.")
        print("💡 You can now safely delete oauth2.json (after confirming it works).")

if __name__ == "__main__":
    migrate()