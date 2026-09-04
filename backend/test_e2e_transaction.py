import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import json
import websockets
import httpx

async def test_full_buyer_loop():
    print("=== STARTING FULL END-TO-END TRANSACTION TEST ===")
    
    # 1. Create Session
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "http://127.0.0.1:8000/api/agent/session",
            json={
                "merchant_id": "merch_DEMO01",
                "purchase_intent": "I want to buy the cheapest cotton kurta",
                "spending_limit_inr": 3000,
            }
        )
        print("Create session response:", resp.status_code, resp.json())
        assert resp.status_code == 200, f"Session create failed: {resp.text}"
        sess_data = resp.json()
        session_id = sess_data["session_id"]
        print(f"Created Session: {session_id}")

    # 2. Connect via WebSocket
    uri = f"ws://127.0.0.1:8000/ws/agent/{session_id}"
    async with websockets.connect(uri, ping_timeout=60, ping_interval=30) as ws:
        print(f"Connected to {uri}")
        
        # Initial handshake info
        info_msg = await ws.recv()
        print("WS session_info:", info_msg)

        # Send purchase request
        prompt = "Please find the best cotton kurta and proceed to purchase it."
        print(f"Sending user prompt: {prompt}")
        await ws.send(json.dumps({"type": "message", "content": prompt}))

        # Listen for events until confirmation_gate or complete
        confirmed_product_id = None
        while True:
            raw = await ws.recv()
            evt = json.loads(raw)
            evt_type = evt.get("type")
            print(f"-> Agent Event [{evt_type}]:", str(evt)[:140])

            if evt_type == "confirmation_gate":
                gate_data = evt.get("data", {})
                confirmed_product_id = gate_data.get("product_id")
                print(f"*** CONFIRMATION GATE TRIGGERED for {gate_data.get('product_name')} (INR {gate_data.get('price_inr')}) ***")
                break
            elif evt_type == "session_complete":
                print("Session completed early:", evt)
                break
            elif evt_type == "error":
                print("Error event received:", evt)
                break

        # If confirmation gate reached, confirm purchase
        if confirmed_product_id:
            print(f"Simulating User Confirmation for product {confirmed_product_id}...")
            await ws.send(json.dumps({
                "type": "confirm",
                "confirmed": True,
                "product_id": confirmed_product_id,
            }))

            # Listen for payment and completion
            while True:
                raw = await ws.recv()
                evt = json.loads(raw)
                evt_type = evt.get("type")
                print(f"-> Post-Confirm Event [{evt_type}]:", str(evt)[:140])

                if evt_type == "session_complete":
                    print("=== TRANSACTION COMPLETED SUCCESSFULLY! ===")
                    print("Completion data:", json.dumps(evt.get("data"), indent=2))
                    break
                elif evt_type == "error":
                    print("Error during payment:", evt)
                    break

    # 3. Verify Audit Trail
    async with httpx.AsyncClient(timeout=30.0) as client:
        audit_resp = await client.get(f"http://127.0.0.1:8000/api/agent/sessions/{session_id}/audit")
        assert audit_resp.status_code == 200
        trail = audit_resp.json()
        print(f"Audit Trail Steps: {len(trail.get('entries', []))}")
        for entry in trail.get("entries", []):
            print(f"  Step {entry['sequence']}: {entry['step']} (Model: {entry.get('model_used')})")
        print("Audit Outcome:", trail.get("outcome"))

if __name__ == "__main__":
    asyncio.run(test_full_buyer_loop())
