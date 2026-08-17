"""Test the medagent API endpoints."""
import httpx
import json
import sys

BASE = "http://localhost:8000/api"

# Login
login = httpx.post(f"{BASE}/auth/login",
    json={"username": "admin", "password": "admin123"}, timeout=10)
token = login.json()["access_token"]
print(f"[OK] Login, token: {token[:20]}...")

# Test streaming endpoint
body = {"question": "你好", "kb_ids": [],
        "web_search_enabled": False, "deep_thinking_enabled": False}

print("\n--- Testing /chat/ask/stream ---")
try:
    resp = httpx.post(f"{BASE}/chat/ask/stream", json=body,
        headers={"Authorization": f"Bearer {token}"}, timeout=60)
    text = resp.text
    print(f"Status: {resp.status_code}")
    print(f"Response length: {len(text)}")

    # Parse events
    answer_tokens = 0
    answer_text = ""
    for line in text.split('\n'):
        if line.startswith('data: '):
            try:
                data = json.loads(line[6:])
                if data.get('type') == 'answer' and data.get('token'):
                    answer_tokens += 1
                    answer_text += data['token']
                if 'error' in data:
                    print(f"ERROR event: {data['error']}")
                if data.get('done'):
                    print(f"DONE event")
            except:
                pass

    print(f"Answer tokens: {answer_tokens}")
    ws = answer_text.strip() == ''
    print(f"Only whitespace: {ws}")
    if not ws:
        print(f"Answer preview: {answer_text[:200]}")
    if answer_tokens == 0:
        print(f"Raw (first 200): {text[:200]}")
except Exception as e:
    print(f"FAILED: {e}")

# Test non-streaming ask
print("\n--- Testing /chat/ask ---")
try:
    resp2 = httpx.post(f"{BASE}/chat/ask", json=body,
        headers={"Authorization": f"Bearer {token}"}, timeout=60)
    data2 = resp2.json()
    answer = data2.get('answer', '')
    ws = answer.strip() == ''
    print(f"Status: {resp2.status_code}")
    print(f"Answer length: {len(answer)}")
    print(f"Only whitespace: {ws}")
    if not ws:
        print(f"Answer preview: {answer[:200]}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== ALL DONE ===")
