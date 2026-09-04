import os
import base64
import requests
import json
from dotenv import load_dotenv

load_dotenv()

key_id = os.getenv("RAZORPAY_KEY_ID")
key_secret = os.getenv("RAZORPAY_KEY_SECRET")
auth_token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()

headers = {
    "Authorization": f"Basic {auth_token}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# 1. Initialize
init_payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "agentic-commerce-buyer", "version": "1.0.0"}
    }
}
resp = requests.post("https://mcp.razorpay.com/mcp", headers=headers, json=init_payload)
print("Init response:", resp.status_code, resp.text[:200])

# 2. List tools
list_payload = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
}
resp = requests.post("https://mcp.razorpay.com/mcp", headers=headers, json=list_payload)
data = resp.json()
tools = data.get("result", {}).get("tools", [])
print(f"Available tools ({len(tools)}):")
for t in tools:
    print(f" - {t['name']}: {t.get('description', '')[:80]}")
