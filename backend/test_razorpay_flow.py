import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

key_id = os.getenv("RAZORPAY_KEY_ID")
key_secret = os.getenv("RAZORPAY_KEY_SECRET")
print(f"Testing with Key ID: {key_id}")

client = razorpay.Client(auth=(key_id, key_secret))

# 1. Test Order creation
order = client.order.create({
    "amount": 50000,
    "currency": "INR",
    "receipt": "rcpt_test_001",
    "notes": {"type": "buildathon_test"}
})
print("Order created successfully:", order["id"], "Status:", order.get("status"))

# 2. Test Payment creation or status fetch
try:
    print("Testing client.payment.create...")
    p = client.payment.create({
        "amount": 50000,
        "currency": "INR",
        "order_id": order["id"],
        "method": "upi",
        "vpa": "success@razorpay"
    })
    print("Payment created:", p)
except Exception as e:
    print("client.payment.create result/error:", type(e), e)

# 3. Test payments list / order payments
try:
    payments = client.order.payments(order["id"])
    print("Order payments:", payments)
except Exception as e:
    print("Order payments error:", type(e), e)
