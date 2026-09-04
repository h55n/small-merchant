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

# 1. Create order via MCP
create_order_payload = {
    "jsonrpc": "2.0",
    "id": 10,
    "method": "tools/call",
    "params": {
        "name": "create_order",
        "arguments": {
            "amount": 25000,
            "currency": "INR",
            "receipt": "mcp_rcpt_01",
            "notes": {"source": "ai_buyer_agent"}
        }
    }
}
resp = requests.post("https://mcp.razorpay.com/mcp", headers=headers, json=create_order_payload)
print("Create order response:", resp.status_code)
res = resp.json()
print("Create order content:", res)

order_id = None
if "result" in res:
    content = res["result"].get("content", [])
    if content:
        parsed = json.loads(content[0]["text"])
        order_id = parsed.get("id")
        print("Created Order ID:", order_id)

# 2. Try initiate_payment via MCP
if order_id:
    pay_payload = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "initiate_payment",
            "arguments": {
                "amount": 25000,
                "order_id": order_id,
                "vpa": "success@razorpay"
            }
        }
    }
    resp2 = requests.post("https://mcp.razorpay.com/mcp", headers=headers, json=pay_payload)
    print("Initiate payment response:", resp2.status_code)
    print("Initiate payment content:", resp2.text)

    # 3. Also test create_payment_link
    link_payload = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {
            "name": "create_payment_link",
            "arguments": {
                "amount": 25000,
                "currency": "INR",
                "description": "Payment for AI Purchase Test"
            }
        }
    }
    resp3 = requests.post("https://mcp.razorpay.com/mcp", headers=headers, json=link_payload)
    print("Payment link raw response:", resp3.text)
    if "result" in resp3.json() and resp3.json()["result"].get("content"):
        txt = resp3.json()["result"]["content"][0]["text"]
        print("Payment link text:", txt)
        try:
            plink_data = json.loads(txt)
            print("Payment link ID:", plink_data.get("id"))
            print("Payment link URL:", plink_data.get("short_url"))
        except Exception:
            pass
