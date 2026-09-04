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

list_payload = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
}
resp = requests.post("https://mcp.razorpay.com/mcp", headers=headers, json=list_payload)
data = resp.json()
tools = data.get("result", {}).get("tools", [])

filtered = {}
for t in tools:
    if t["name"] in ["create_order", "initiate_payment", "create_payment_link", "fetch_order", "fetch_payment", "create_qr_code"]:
        filtered[t["name"]] = {
            "description": t["description"],
            "inputSchema": t.get("inputSchema", {})
        }

with open("mcp_selected_schemas.json", "w", encoding="utf-8") as f:
    json.dump(filtered, f, indent=2, ensure_ascii=False)

print("Saved schemas successfully for:", list(filtered.keys()))
