import os
from dotenv import load_dotenv, find_dotenv
from supabase import create_client, Client

# 1. Force load the .env file
load_dotenv(find_dotenv(), override=True)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ Error: Missing credentials.")
    supabase = None
else:
    # 2. Initialize Standard Client
    # With the prefix removed from your .env, this will work automatically.
    supabase: Client = create_client(url, key)
    print(f"🚀 PuckNexus: Connection Initialized")