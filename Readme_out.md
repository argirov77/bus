Backend:

bash
Copy
Edit
cd backend
python3 -m venv venv
source venv/bin/activate      # или .\venv\Scripts\Activate на Windows
pip install -r requirements.txt
# убедитесь, что DATABASE_URL в .env или default в code указывает на вашу БД
uvicorn main:app --reload


Frontend:

bash
Copy
Edit
cd frontend
npm ci              # или: yarn install
npm start   