import os

# The CORRECT long key (without the 'sb_secret_' prefix)
CORRECT_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh5YXV2dml0bHRnanBzZW5tZHNuIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTk0Mzk1NCwiZXhwIjoyMDg3NTE5OTU0fQ.lzUZc6JzBaRio_DN0lHEvEt3d16PBqf6nbEzle4cKgU"

env_path = ".env"

def fix_env_file():
    # Read the current file
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
    else:
        lines = []

    new_lines = []
    key_fixed = False

    for line in lines:
        if line.startswith("SUPABASE_KEY="):
            # Replace the bad line with the good one
            new_lines.append(f'SUPABASE_KEY="{CORRECT_KEY}"\n')
            key_fixed = True
            print("✅ Found and corrected SUPABASE_KEY.")
        else:
            new_lines.append(line)

    # If key wasn't found, append it
    if not key_fixed:
        new_lines.append(f'SUPABASE_KEY="{CORRECT_KEY}"\n')
        print("✅ Added missing SUPABASE_KEY.")

    # Write back to file
    with open(env_path, "w") as f:
        f.writelines(new_lines)
    
    print("🎉 .env file has been successfully repaired!")

if __name__ == "__main__":
    fix_env_file()