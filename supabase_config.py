import os
from dotenv import load_dotenv, find_dotenv
from supabase import create_client, Client

load_dotenv(find_dotenv(), override=True)

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ Error: Missing credentials.")
    supabase = None
else:
    supabase: Client = create_client(url, key)
    print(f"🚀 PuckNexus: Connection Initialized")