# WorkSphere HRMS – Phase 3

Automation, Insights & Smart HR Features.

Modules 14–20: shift management, leave calendar, documents, performance, analytics, notifications, and advanced employee search.

## Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

Swagger: http://127.0.0.1:8000/docs

## Frontend
cd frontend
npm install
npm run dev

Frontend: http://localhost:5173/

Demo: admin/Admin@123, hr/Hr@123, employee/Employee@123
