import os

# Создаем requirements.txt для бэкенда
requirements_content = """fastapi==0.95.2
uvicorn==0.22.0
psycopg2==2.9.6
pydantic==1.10.7
"""

with open("requirements.txt", "w", encoding="utf-8") as f:
    f.write(requirements_content)
print("requirements.txt создан в корне бэкенда.")

# Создаем package.json для фронтенда
package_json_content = """{
  "name": "frontend",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.3.4",
    "@dnd-kit/core": "^6.0.6",
    "@dnd-kit/sortable": "^6.0.6",
    "@dnd-kit/utilities": "^6.0.6"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject"
  }
}
"""

frontend_dir = "frontend"
if not os.path.exists(frontend_dir):
    print("Каталог 'frontend' не найден!")
else:
    package_json_path = os.path.join(frontend_dir, "package.json")
    with open(package_json_path, "w", encoding="utf-8") as f:
        f.write(package_json_content)
    print("package.json создан в каталоге 'frontend'.")
