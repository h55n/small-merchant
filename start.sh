#!/bin/bash
echo "Starting backend on :8000 and frontend on :5173..."
cd backend/
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ../frontend/
npm run dev &
FRONTEND_PID=$!
echo "Backend PID: $BACKEND_PID | Frontend PID: $FRONTEND_PID"
echo "Press Ctrl+C to stop both"
trap "kill $BACKEND_PID $FRONTEND_PID" INT
wait
