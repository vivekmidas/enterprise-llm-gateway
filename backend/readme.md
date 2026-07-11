sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' .dump > backend/extras/db.sql
sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' < backend/extras/db.sql
sqlite3 '/Users/vivekjain/projects/enterprise-llm-gateway/backend/enterprise_gateway.db' < backend/extras/sanitize.sql