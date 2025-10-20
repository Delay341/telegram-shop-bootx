
import os, time, json, requests, hashlib, sys, traceback

GIST_ID = os.getenv("GIST_ID", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
FILE_PATH = os.getenv("BALANCES_FILE", "balances.json")
INTERVAL = int(os.getenv("GIST_SYNC_INTERVAL", "20"))  # seconds

API_URL = f"https://api.github.com/gists/{GIST_ID}" if GIST_ID else None
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

def sha1(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def load_local() -> str:
    if not os.path.exists(FILE_PATH):
        open(FILE_PATH, "w", encoding="utf-8").write("{}\n")
        return "{}\n"
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        return f.read()

def save_local(content: str):
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(content if content.endswith("\n") else content + "\n")

def get_remote() -> str | None:
    try:
        r = requests.get(API_URL, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json()
            files = data.get("files", {})
            if "balances.json" in files and files["balances.json"] and files["balances.json"].get("content") is not None:
                return files["balances.json"]["content"]
        elif r.status_code == 404:
            return None
        else:
            print(f"[gist] GET failed {r.status_code}: {r.text[:200]}", flush=True)
    except Exception as e:
        print("[gist] GET error:", e, flush=True)
    return None

def patch_remote(content: str) -> bool:
    payload = {"files": {"balances.json": {"content": content}}}
    try:
        r = requests.patch(API_URL, headers=HEADERS, json=payload, timeout=30)
        if r.status_code in (200, 201):
            return True
        print(f"[gist] PATCH failed {r.status_code}: {r.text[:200]}", flush=True)
    except Exception as e:
        print("[gist] PATCH error:", e, flush=True)
    return False

def ensure_creds():
    if not GIST_ID or not GITHUB_TOKEN:
        print("⚠️  GIST balance sync disabled (GIST_ID or GITHUB_TOKEN not set).", flush=True)
        sys.exit(0)

def main():
    ensure_creds()
    print("🧩 Gist sync starting…", flush=True)

    remote = get_remote()
    if remote is None:
        print("ℹ️  Remote balances.json not found — creating.", flush=True)
        patch_remote("{}\n")
        remote = "{}\n"

    local = load_local()

    try:
        if local.strip() in ("", "{}") and remote.strip() not in ("", "{}"):
            save_local(remote)
            local = remote
            print("⬇️  Pulled balances from Gist.", flush=True)
    except Exception:
        import traceback; traceback.print_exc()

    last_local_hash = sha1(local)
    last_remote_hash = sha1(remote)

    while True:
        time.sleep(INTERVAL)
        # push local updates
        try:
            current = load_local()
            if sha1(current) != last_local_hash:
                if patch_remote(current):
                    last_local_hash = sha1(current)
                    last_remote_hash = last_local_hash
                    print("⬆️  Pushed balances.json to Gist.", flush=True)
        except Exception:
            import traceback; traceback.print_exc()

        # pull remote changes (manual edits)
        try:
            new_remote = get_remote()
            if new_remote is not None and sha1(new_remote) != last_remote_hash:
                save_local(new_remote)
                last_remote_hash = sha1(new_remote)
                last_local_hash  = last_remote_hash
                print("⬇️  Pulled remote balances.json from Gist.", flush=True)
        except Exception:
            import traceback; traceback.print_exc()

if __name__ == "__main__":
    main()
