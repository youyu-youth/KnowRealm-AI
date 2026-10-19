export const materialExamples = [
  {
    key: "compose",
    filename: "docker-compose.yml",
    code: 'services:\n  web:\n    image: nginx:alpine\n    ports:\n      - "8080:80"\n  db:\n    image: mysql:8.4',
  },
  {
    key: "mysql",
    filename: "init.sql",
    code: "CREATE DATABASE IF NOT EXISTS study;\nUSE study;\nCREATE TABLE notes (\n  id BIGINT PRIMARY KEY,\n  content TEXT NOT NULL\n);",
  },
  {
    key: "nginx",
    filename: "nginx.conf",
    code: "server {\n  listen 80;\n  location / {\n    root /usr/share/nginx/html;\n    index index.html;\n  }\n}",
  },
] as const;
