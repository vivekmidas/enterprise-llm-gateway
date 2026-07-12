PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE categories (
    id INTEGER NOT NULL,
    "group" VARCHAR,
    icon VARCHAR,
    color VARCHAR,
    label VARCHAR,
    description VARCHAR,
    PRIMARY KEY (id)
);
INSERT INTO categories VALUES(1,'LLM Engines','Brain','#8b5cf6','Large Language Model','Core language model execution points and agent instances');
INSERT INTO categories VALUES(2,'Safety Guardrails','ShieldAlert','#ef4444','Guard Rails','Real-time validators for safety, compliance, and PII masking.');
INSERT INTO categories VALUES(3,'External Systems','box','#0A1dde','External Systems','Call external Systems');
INSERT INTO categories VALUES(4,'Communicaation','mail','#ff000a','Mails','Mails, SMS, WhatsAPP etc..');
INSERT INTO categories VALUES(5,'Data Operations','database','#06b6d4','Databases','DB queries, API calls, and inline scripts/variable setters.');
INSERT INTO categories VALUES(6,'Control Logic','gitfork','#f59e0b','Logic','Conditional routers, branching, and data transformations');
INSERT INTO categories VALUES(7,'Context & Memory','history','#3b82f6','Memory',unistr('Chat history managers and context injection helpers.\u0009Context Setter, Session Memory, RAG Embeddings\u000aAlerts\u0009Notifications\u0009Bell\u0009Orange (#f97316)\u0009Integration points for sending logs, emails, or chat alerts.\u0009Slack Notification, Send SMTP Mail, Audit Logger\u000a8. Alignment Implementation Steps\u000aDatabase Migration: Update backend/app/core/db.sql and run a schema migration to seed the categories table with the new IDs, colors, icons, and descriptions matching the grid above.\u000aFrontend Synchronization: Update frontend/app/components/component-categoriees.ts to map the CATEGORIES record to match the backend database labels and icons.\u000aPalette UI Revamp: Adjust the sidebar selector categories to display badges matching the Visual Theme colors for a clean cockpit feeling.\u000a'));
INSERT INTO categories VALUES(9,'Alerts','bell','#f97316','Integration','Integration points for sending logs, emails, or chat alerts.');
INSERT INTO categories VALUES(10,'Vector Databases','blocks','#10b981','Vector DB','Store and query high-dimensional vector embeddings.');
CREATE TABLE credentials (
    id INTEGER NOT NULL,
    name VARCHAR,
    type VARCHAR NOT NULL,
    config JSON NOT NULL,
    auth_data JSON,
    created_at VARCHAR,
    updated_at VARCHAR,
    PRIMARY KEY (id)
);
CREATE TABLE oauth_providers (
    id INTEGER NOT NULL,
    name VARCHAR,
    label VARCHAR,
    description VARCHAR,
    auth_url VARCHAR,
    token_url VARCHAR,
    default_scopes VARCHAR,
    callback_url VARCHAR,
    icon VARCHAR,
    PRIMARY KEY (id)
);
INSERT INTO oauth_providers VALUES(0,'google','Google OAuth Provider','Validates and get auth details from Google','http://localhost:3000/api/oauth/google/connect',NULL,NULL,'http://localhost:3000/api/oauth/google/callback',NULL);
CREATE TABLE IF NOT EXISTS "users" (
    id INTEGER NOT NULL,
    username VARCHAR,
    email_id VARCHAR,
    password VARCHAR NOT NULL,
    name VARCHAR,
    customer_id VARCHAR,
    status VARCHAR,
    role VARCHAR,
    created_at VARCHAR,
    updated_at VARCHAR,
    PRIMARY KEY (id),
    FOREIGN KEY (customer_id) REFERENCES customers (id)
);
INSERT INTO users VALUES(1,'admin@gateway.com','admin@gateway.com','$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI','System Admin','0','active','system_admin','2026-06-15T06:54:24.944840','2026-06-15T06:54:24.944863');
INSERT INTO users VALUES(2,'vivek@midasminds.in','vivek@midasminds.in','$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI','Vivek Jain','1','active','user','2026-06-15T07:02:43.832758','2026-06-15T07:02:43.832776');
INSERT INTO users VALUES(5,'admin@midasminds.com','admin@midasminds.com','$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI','Admin','1','active','admin','2026-06-27T16:54:47.398860','2026-06-27T16:54:47.398898');
INSERT INTO users VALUES(6,'x@test.com','x@test.com','$argon2id$v=19$m=1024,t=2,p=8$Yx05319A/5T52EIuxnluvA$vBKsUmuAFfaOZrc1k2ovDJaD1LKCTsJmXS9yUQtbTfo','x','0','active','admin','2026-06-28T20:06:27.444339','2026-06-28T20:06:27.444361');
INSERT INTO users VALUES(1001,'owner@example.com','owner@example.com','password','User 1001','999','active','user','2026-07-11T07:23:11.560834','2026-07-11T07:23:11.560839');
INSERT INTO users VALUES(1002,'admin@example.com','admin@example.com','password','User 1002','999','active','admin','2026-07-11T07:23:11.561920','2026-07-11T07:23:11.561925');
INSERT INTO users VALUES(1003,'other@example.com','other@example.com','password','User 1003','998','active','user','2026-07-11T07:23:11.562432','2026-07-11T07:23:11.562435');
INSERT INTO users VALUES(1004,'owner2@example.com','owner2@example.com','password','User 1004','999','active','user','2026-07-11T07:23:11.588952','2026-07-11T07:23:11.588959');
INSERT INTO users VALUES(2001,'sysadmin@example.com','sysadmin@example.com','pwd','SysAdmin',NULL,'active','system_admin','2026-07-11T07:23:11.610479','2026-07-11T07:23:11.610483');
INSERT INTO users VALUES(12345,'test_auth_me@example.com','test_auth_me@example.com','password','Test Auth Me',NULL,'active','admin','2026-07-11T07:23:11.638948','2026-07-11T07:23:11.638952');
INSERT INTO users VALUES(12346,'acme_user_eo_1783754591@acme.com','acme_user_eo_1783754591@acme.com','$argon2id$v=19$m=1024,t=2,p=8$fLh+2BvIL1+MaD7UNcG+Kw$1K0KK3tWv/SCaaXxP+fNm5nLFdeaouG6KIMRsvOAQpQ','Acme User','2','active','user','2026-07-11T07:23:11.953981','2026-07-11T07:23:11.953984');
INSERT INTO users VALUES(12350,'acme_user_props_1783754596@acme.com','acme_user_props_1783754596@acme.com','$argon2id$v=19$m=1024,t=2,p=8$Znr+6OUUlFq4jsaUW6MJ5g$Kg0Zk4MKPM0jSYK/AcyWWt4RpmYzgCdUrn4ztWlf5sA','Acme User','5','active','user','2026-07-11T07:23:16.077043','2026-07-11T07:23:16.077047');
INSERT INTO users VALUES(12351,'acme_user_eo_1783759454@acme.com','acme_user_eo_1783759454@acme.com','$argon2id$v=19$m=1024,t=2,p=8$kpR2EljorI3iJ+rD9ZT2lw$H+qrAWy2RqHhBf3jXUza9LWjnsLFkeNd2BAok3VD+ck','Acme User','6','active','user','2026-07-11T08:44:14.142029','2026-07-11T08:44:14.142033');
INSERT INTO users VALUES(12352,'log_acme_admin@acme.com','log_acme_admin@acme.com','$argon2id$v=19$m=1024,t=2,p=8$+PPcFwBUtzm0/pXfMFRpXA$M2vzCczdTCJiiAWaCPkrGaN7vI5b/h7LHHaww1T1iIA','Acme Log Admin','7','active','admin','2026-07-11T08:44:18.031366','2026-07-11T08:44:18.031369');
INSERT INTO users VALUES(12353,'log_acme_user@acme.com','log_acme_user@acme.com','$argon2id$v=19$m=1024,t=2,p=8$NQrcpPXdrsOOU4imxLw/4A$+A2x5AONdjsEDy6BZx4PqTHC96QA/jyT9mLOe2akbII','Acme Log User','7','active','user','2026-07-11T08:44:18.035203','2026-07-11T08:44:18.035206');
INSERT INTO users VALUES(12354,'log_globex_admin@globex.com','log_globex_admin@globex.com','$argon2id$v=19$m=1024,t=2,p=8$s13v2W4L7pCrCwMtjXvaqA$Lrj9vYZy36x07Q4e/sRdxXSsognwoBZeXHnVM4Sos0Y','Globex Admin','8','active','admin','2026-07-11T08:44:18.045945','2026-07-11T08:44:18.045948');
INSERT INTO users VALUES(12355,'acme_user_props_1783759458@acme.com','acme_user_props_1783759458@acme.com','$argon2id$v=19$m=1024,t=2,p=8$afHbZFVzDWIYLSL1KHLfVw$LAYkrOCtUriZP8uTwLH08eJN6Qq2WwE93po9+R9fCuo','Acme User','9','active','user','2026-07-11T08:44:18.150466','2026-07-11T08:44:18.150470');
CREATE TABLE IF NOT EXISTS "workflows" (
    id VARCHAR NOT NULL,
    name VARCHAR,
    description VARCHAR,
    version INTEGER,
    edges Varchar,
    category VARCHAR,
    nodes_structure varchar,
    definition JSON,
    updated_at VARCHAR,
    is_enabled Boolean,
    customer_id varchar not null,
    user_id varchar not NULL, is_runnable BOOLEAN DEFAULT 1,
    PRIMARY KEY (id),
    FOREIGN KEY (customer_id) REFERENCES customers (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);
INSERT INTO workflows VALUES('external_api','External API','',1,NULL,'default',NULL,'{"nodes": [{"id": "api_webhook_agent_1782579449688", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "api_webhook_agent", "label": "Base Web hook", "description": "API Webhook Agent for external system integration", "category": "2", "icon": "Cloud", "id": 9, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#7C3AED", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [{"key": "port", "default": "8888"}, {"key": "host", "default": "0.0.0.0"}, {"key": "workers", "default": "1"}], "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "executionStatus": "idle", "variant": "2", "subIcon": "Cloud", "model": "", "properties": {}}, "position": {"x": -166, "y": 93}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "external_api_node_1782579453575", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "external_api_node", "label": "External API", "description": "Calls the third party API ", "category": "1", "icon": "Cloud", "id": 10, "node_type": "NODE", "version": "1.0.0", "group": "", "color": "#5E0CEC", "badge": "Node", "sub_label": "", "user_properties": [{"key": "url", "default": "www.bing.com/search"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "auth_key", "default": ""}, {"key": "path", "default": "/search"}, {"key": "api_path", "default": ""}, {"key": "params", "default": "[{\"q\":\"{{message}}\"}]"}, {"key": "auth_type", "default": "API_KEY"}], "system_properties": [{"key": "host", "default": "www.bing.com"}, {"key": "auth_type", "default": "API_KEY"}], "category_id": 1, "category_color": "#8b5cf6", "is_enabled": true, "executionStatus": "idle", "variant": "1", "subIcon": "Cloud", "model": "", "properties": {"url": "www.bing.com", "protocol": "https", "method": "GET", "auth_key": "", "path": "/search", "api_path": "", "params": "[{\"q\":\"{{message}}\"}]", "auth_type": "API_KEY", "host": "www.bing.com", "mapping_template": "{\n  \"data\": \"{{ input_data.result }}\"\n}"}}, "position": {"x": 306, "y": 86.5}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "api_webhook_agent_1782579449688", "sourceHandle": "source-right", "target": "external_api_node_1782579453575", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__api_webhook_agent_1782579449688source-right-external_api_node_1782579453575target-left", "selected": true}], "entry_point": "input_guard"}','2026-07-07T16:32:07.120914',1,'1','2',1);
INSERT INTO workflows VALUES('sentiment_analyis','Sentiment Analyis','',1,NULL,'default',NULL,'{"nodes": [{"id": "sentiment_analyzer_1782672296380", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "sentiment_analyzer", "label": "Sentiment Analyzer 989", "description": "Analyzes sentiment of user message", "category": "3", "icon": "bot", "id": 8, "node_type": "NODE", "version": "1.0.0", "group": null, "color": "#12239e", "badge": "Node", "sub_label": null, "user_properties": [{"key": "sentiment", "default": "1"}, {"key": "another", "default": "a"}], "system_properties": [{"key": "sentiment", "default": "1"}], "category_id": 3, "category_color": "#0A1dde", "is_enabled": true, "executionStatus": "idle", "variant": "3", "subIcon": "bot", "model": "", "properties": {"sentiment": "1", "another": "a"}}, "position": {"x": 238.5, "y": 88.25}, "measured": {"width": 210, "height": 56}, "selected": true}, {"id": "scheduler_agent_1782935753755", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "scheduler_agent", "label": "Scheduler", "description": "Trigger scheder after n seconds", "category": "2", "icon": "Clock", "id": 7, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#0000CC", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [], "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "executionStatus": "idle", "variant": "2", "subIcon": "Clock", "model": ""}, "position": {"x": -186.75, "y": -25.375}, "measured": {"width": 210, "height": 56}}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "scheduler_agent_1782935753755", "sourceHandle": "source-right", "target": "sentiment_analyzer_1782672296380", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__scheduler_agent_1782935753755source-right-sentiment_analyzer_1782672296380target-left"}], "entry_point": "input_guard"}','2026-07-11T10:09:34.287385',0,'1','2',1);
INSERT INTO workflows VALUES('eod_stocks','EOD Stocks','',1,NULL,'default',NULL,'{"nodes": [{"id": "stocks_api_request_node_1782722681073", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "stocks_api_request_node", "label": "EODHD Stocks", "description": "Calls EODHD for stock details", "category": "1", "icon": "bot", "id": 18, "node_type": "NODE", "version": "1.0.0", "group": "Custom", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": {"mapping_template": "{\n  \"stock_token\": \"{{stock_token}}\",\n  \"fmt\": \"{{fmt}}\"\n}"}, "system_properties": {"auth_key": "", "url": "eodhd.com", "protocol": "https", "method": "GET", "params": "api_token=69747bd28b3bd8.99561497&fmt=json", "auth_type": "NONE", "path": "/api/eod/{{stock_token}}", "api_path": ""}, "category_id": 1, "category_color": "#8b5cf6", "is_enabled": true, "properties": {"auth_key": "", "url": "eodhd.com", "protocol": "https", "method": "GET", "params": "api_token=69747bd28b3bd8.99561497&fmt=json", "auth_type": "NONE", "path": "/api/eod/{{stock_token}}", "api_path": "", "mapping_template": "{\n  \"stock_token\": \"{{stock_token}}\",\n  \"fmt\": \"{{fmt}}\"\n}"}, "executionStatus": "idle", "variant": "1", "subIcon": "bot", "model": "", "input_contract": {"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}, {"field_name": "fmt", "field_type": "string", "required": true}], "additional_fields": true}, "output_contract": {"version": "1.0", "rules": [{"field_name": "root[].date", "field_type": "phone", "required": false}, {"field_name": "root[].open", "field_type": "number", "required": false}, {"field_name": "root[].high", "field_type": "number", "required": false}, {"field_name": "root[].low", "field_type": "number", "required": false}, {"field_name": "root[].close", "field_type": "number", "required": false}, {"field_name": "root[].adjusted_close", "field_type": "number", "required": false}, {"field_name": "root[].volume", "field_type": "integer", "required": false}]}, "property_schema": [{"key": "auth_key", "default": "", "value": ""}, {"key": "url", "default": "eodhd.com", "value": "eodhd.com"}, {"key": "protocol", "default": "https", "value": "https"}, {"key": "method", "default": "GET", "value": "GET"}, {"key": "params", "default": "api_token=69747bd28b3bd8.99561497&fmt=json", "value": "api_token=69747bd28b3bd8.99561497&fmt=json"}, {"key": "auth_type", "default": "NONE", "value": "NONE"}, {"key": "path", "default": "/api/eod/{{stock_token}}", "value": "/api/eod/{{stock_token}}"}, {"key": "api_path", "default": "", "value": ""}, {"key": "mapping_template", "type": "textarea", "label": "Mapping Template", "default": "", "value": "{\n  \"stock_token\": \"{{stock_token}}\",\n  \"fmt\": \"{{fmt}}\"\n}"}], "propertySchema": [{"key": "auth_key", "default": "", "value": ""}, {"key": "url", "default": "eodhd.com", "value": "eodhd.com"}, {"key": "protocol", "default": "https", "value": "https"}, {"key": "method", "default": "GET", "value": "GET"}, {"key": "params", "default": "api_token=69747bd28b3bd8.99561497&fmt=json", "value": "api_token=69747bd28b3bd8.99561497&fmt=json"}, {"key": "auth_type", "default": "NONE", "value": "NONE"}, {"key": "path", "default": "/api/eod/{{stock_token}}", "value": "/api/eod/{{stock_token}}"}, {"key": "api_path", "default": "", "value": ""}, {"key": "mapping_template", "type": "textarea", "label": "Mapping Template", "default": "", "value": "{\n  \"stock_token\": \"{{stock_token}}\",\n  \"fmt\": \"{{fmt}}\"\n}"}]}, "position": {"x": 359, "y": -307}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "stocks_webhook_agent_1782723972280", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "stocks_webhook_agent", "label": "Stocks Webhook Agent", "description": "Triggers workflows on stock price movements or API alerts", "category": "1", "icon": "bot", "id": 17, "node_type": "TRIGGER", "version": "1.0.0", "group": "Custom", "color": "#2ECC71", "badge": "Node", "sub_label": null, "user_properties": {"required_fields": ["stock_token", "market", "fmt"], "stateable_fields": ["stock_token", "market", "fmt"]}, "system_properties": {"port": "8888", "host": "0.0.0.0", "base_path": "stocks"}, "category_id": 1, "category_color": "#8b5cf6", "is_enabled": true, "properties": {"port": "8888", "host": "0.0.0.0", "base_path": "stocks", "required_fields": ["stock_token", "market", "fmt"], "stateable_fields": ["stock_token", "market", "fmt"]}, "executionStatus": "idle", "variant": "1", "subIcon": "bot", "model": "", "input_contract": {"version": "1.0", "rules": [], "additional_fields": true}, "output_contract": {"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": false}, {"field_name": "fmt", "field_type": "string", "required": false}, {"field_name": "market", "field_type": "string", "required": false}]}, "property_schema": [{"key": "port", "default": "8888", "value": "8888"}, {"key": "host", "default": "0.0.0.0", "value": "0.0.0.0"}, {"key": "base_path", "default": "stocks", "value": "stocks"}], "propertySchema": [{"key": "port", "default": "8888", "value": "8888"}, {"key": "host", "default": "0.0.0.0", "value": "0.0.0.0"}, {"key": "base_path", "default": "stocks", "value": "stocks"}]}, "position": {"x": -17, "y": -148.5}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "generic_mysql_query_executor_1782763274758", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_mysql_query_executor", "label": "MySQL Node", "description": "Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.", "category": "5", "icon": "bot", "id": 20, "node_type": "NODE", "version": "1.0.0", "group": "Data", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": {"database": "test", "table": "stocks", "query_type": "insert", "mapping_template": "{\n  \"field_names\": [\n    \"date\",\n    \"close\",\n    \"open\"\n  ],\n  \"field_values\": [\n    \"{{root[].date}}\",\n    \"{{root[].open}}\",\n    \"{{root[].close}}\"\n  ]\n}"}, "system_properties": {"db_port": "3306", "user_name": "root", "db_host": "127.0.0.1", "password": "password", "secured": "false"}, "category_id": 5, "category_color": "#06b6d4", "is_enabled": true, "executionStatus": "idle", "variant": "5", "subIcon": "bot", "model": "", "properties": {"db_port": "3306", "user_name": "root", "db_host": "127.0.0.1", "password": "password", "secured": "false", "database": "test", "table": "stocks", "query_type": "insert", "mapping_template": "{\n  \"field_names\": [\n    \"date\",\n    \"close\",\n    \"open\"\n  ],\n  \"field_values\": [\n    \"{{root[].date}}\",\n    \"{{root[].open}}\",\n    \"{{root[].close}}\"\n  ]\n}"}, "input_contract": {"version": "1.0", "rules": [{"field_name": "query_type", "field_type": "string", "required": false}, {"field_name": "query", "field_type": "string", "required": false}, {"field_name": "table_name", "field_type": "string", "required": false}, {"field_name": "fields", "field_type": "object", "required": false}, {"field_name": "field_names", "field_type": "array", "required": false}, {"field_name": "field_values", "field_type": "array", "required": false}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": "True"}, "output_contract": {"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": true, "stateable": false}, {"field_name": "lastrowid", "field_type": "integer", "required": true, "stateable": false}]}, "property_schema": [{"key": "database", "test": "default", "value": "test", "label": "database", "type": "string", "default": "", "description": ""}, {"key": "table", "label": "Table Name", "type": "string", "value": "stocks", "default": "", "description": ""}, {"key": "query_type", "label": "Query Type ", "type": "choice", "value": "insert", "default": "", "description": ""}, {"key": "db_port", "label": "db_port", "type": "string", "value": "3306", "default": "3306", "description": ""}, {"key": "user_name", "label": "user_name", "type": "string", "value": "root", "default": "admin", "description": ""}, {"key": "db_host", "label": "db_host", "type": "string", "value": "127.0.0.1", "default": "127.0.0.1", "description": ""}, {"key": "password", "label": "password", "type": "string", "value": "password", "default": "password", "description": ""}, {"key": "secured", "label": "secured", "type": "string", "value": "false", "default": "false", "description": ""}, {"key": "mapping_template", "type": "textarea", "label": "Mapping Template", "default": "", "value": "{\n  \"field_names\": [\n    \"date\",\n    \"close\",\n    \"open\"\n  ],\n  \"field_values\": [\n    \"{{root[].date}}\",\n    \"{{root[].open}}\",\n    \"{{root[].close}}\"\n  ]\n}"}], "propertySchema": [{"key": "database", "test": "default", "value": "test", "label": "database", "type": "string", "default": "", "description": ""}, {"key": "table", "label": "Table Name", "type": "string", "value": "stocks", "default": "", "description": ""}, {"key": "query_type", "label": "Query Type ", "type": "choice", "value": "insert", "default": "", "description": ""}, {"key": "db_port", "label": "db_port", "type": "string", "value": "3306", "default": "3306", "description": ""}, {"key": "user_name", "label": "user_name", "type": "string", "value": "root", "default": "admin", "description": ""}, {"key": "db_host", "label": "db_host", "type": "string", "value": "127.0.0.1", "default": "127.0.0.1", "description": ""}, {"key": "password", "label": "password", "type": "string", "value": "password", "default": "password", "description": ""}, {"key": "secured", "label": "secured", "type": "string", "value": "false", "default": "false", "description": ""}, {"key": "mapping_template", "type": "textarea", "label": "Mapping Template", "default": "", "value": "{\n  \"field_names\": [\n    \"date\",\n    \"close\",\n    \"open\"\n  ],\n  \"field_values\": [\n    \"{{root[].date}}\",\n    \"{{root[].open}}\",\n    \"{{root[].close}}\"\n  ]\n}"}]}, "position": {"x": 563.3308510638298, "y": -138.07074468085108}, "measured": {"width": 210, "height": 56}, "selected": true, "dragging": false}, {"id": "generic_mysql_query_executor_1783670890311", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_mysql_query_executor", "label": "MySQL Node", "description": "Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.", "category": "5", "icon": "bot", "id": 20, "node_type": "NODE", "version": "1.0.0", "group": "Data", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": [{"key": "database", "test": "default", "value": "test", "label": "database", "type": "string", "default": "", "description": ""}, {"key": "table", "label": "Table Name", "type": "string", "value": "temp", "default": "", "description": ""}, {"key": "query_type", "label": "Query Type ", "type": "choice", "value": "insert,delete,update,select", "default": "", "description": ""}], "system_properties": [{"key": "db_port", "label": "db_port", "type": "string", "value": "3306", "default": "3306", "description": ""}, {"key": "user_name", "label": "user_name", "type": "string", "value": "root", "default": "admin", "description": ""}, {"key": "db_host", "label": "db_host", "type": "string", "value": "127.0.0.1", "default": "127.0.0.1", "description": ""}, {"key": "password", "label": "password", "type": "string", "value": "password", "default": "password", "description": ""}, {"key": "secured", "label": "secured", "type": "string", "value": "false", "default": "false", "description": ""}], "input_contract": {"version": "1.0", "rules": [{"field_name": "table_name", "field_type": "string", "required": true}, {"field_name": "fields", "field_type": "object", "required": true}, {"field_name": "field_names", "field_type": "array", "required": true}, {"field_name": "field_values", "field_type": "array", "required": true}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": true}, "output_contract": {"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": "False"}, {"field_name": "lastrowid", "field_type": "integer", "required": "False"}], "additional_fields": "True"}, "category_id": 5, "category_color": "#06b6d4", "is_enabled": true, "propertySchema": [], "properties": {"db_port": "3306", "user_name": "root", "db_host": "127.0.0.1", "password": "password", "secured": "false", "database": "test", "table": "temp", "query_type": "insert,delete,update,select"}, "executionStatus": "idle", "variant": "5", "subIcon": "bot", "model": "", "property_schema": []}, "position": {"x": 594.3164893617021, "y": -421.8598404255319}, "measured": {"width": 210, "height": 56}, "selected": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "stocks_webhook_agent_1782723972280", "sourceHandle": "source-right", "target": "stocks_api_request_node_1782722681073", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__stocks_webhook_agent_1782723972280source-right-stocks_api_request_node_1782722681073target-left"}, {"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "stocks_api_request_node_1782722681073", "sourceHandle": "source-right", "target": "generic_mysql_query_executor_1782763274758", "targetHandle": "target-left", "condition": "success", "data": {"condition": "success", "expression": ""}, "id": "xy-edge__stocks_api_request_node_1782722681073source-right-generic_mysql_query_executor_1782763274758target-left", "selected": false, "expression": ""}, {"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "stocks_api_request_node_1782722681073", "sourceHandle": "source-right", "target": "generic_mysql_query_executor_1783670890311", "targetHandle": "target-left", "condition": "failure", "data": {"condition": "failure", "expression": ""}, "id": "xy-edge__stocks_api_request_node_1782722681073source-right-generic_mysql_query_executor_1783670890311target-left", "selected": false, "expression": ""}], "entry_point": "input_guard"}','2026-07-10T08:10:40.759207',1,'1','1',1);
INSERT INTO workflows VALUES('mysql','MySQL','',1,NULL,'default',NULL,'{"nodes": [{"id": "generic_mysql_query_executor_1782762522453", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_mysql_query_executor", "label": "MySQL Node", "description": "Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.", "category": "5", "icon": "bot", "id": 20, "node_type": "NODE", "version": "1.0.0", "group": "Data", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": {"database": "test", "table": "stocks", "query_type": "select"}, "system_properties": {"db_port": "3306", "user_name": "admin", "db_host": "127.0.0.1", "password": "password", "secured": "false"}, "category_id": 5, "category_color": "#06b6d4", "is_enabled": true, "executionStatus": "idle", "variant": "5", "subIcon": "bot", "model": "", "properties": {"db_port": "3306", "user_name": "admin", "db_host": "127.0.0.1", "password": "password", "secured": "false", "database": "test", "table": "stocks", "query_type": "select"}, "input_contract": {"version": "1.0", "rules": [{"field_name": "query_type", "field_type": "string", "required": false}, {"field_name": "query", "field_type": "string", "required": false}, {"field_name": "table_name", "field_type": "string", "required": false}, {"field_name": "fields", "field_type": "object", "required": false}, {"field_name": "field_names", "field_type": "array", "required": false}, {"field_name": "field_values", "field_type": "array", "required": false}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": "True"}, "output_contract": {"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": "False", "stateable": true}, {"field_name": "lastrowid", "field_type": "integer", "required": "False", "stateable": true}], "additional_fields": "True"}, "property_schema": [{"key": "database", "test": "default", "value": "test", "label": "database", "type": "string", "default": "", "description": ""}, {"key": "table", "label": "Table Name", "type": "string", "value": "stocks", "default": "", "description": ""}, {"key": "query_type", "label": "Query Type ", "type": "choice", "value": "select", "default": "", "description": ""}, {"key": "db_port", "label": "db_port", "type": "string", "value": "3306", "default": "3306", "description": ""}, {"key": "user_name", "label": "user_name", "type": "string", "value": "admin", "default": "admin", "description": ""}, {"key": "db_host", "label": "db_host", "type": "string", "value": "127.0.0.1", "default": "127.0.0.1", "description": ""}, {"key": "password", "label": "password", "type": "string", "value": "password", "default": "password", "description": ""}, {"key": "secured", "label": "secured", "type": "string", "value": "false", "default": "false", "description": ""}], "propertySchema": [{"key": "database", "test": "default", "value": "test", "label": "database", "type": "string", "default": "", "description": ""}, {"key": "table", "label": "Table Name", "type": "string", "value": "stocks", "default": "", "description": ""}, {"key": "query_type", "label": "Query Type ", "type": "choice", "value": "select", "default": "", "description": ""}, {"key": "db_port", "label": "db_port", "type": "string", "value": "3306", "default": "3306", "description": ""}, {"key": "user_name", "label": "user_name", "type": "string", "value": "admin", "default": "admin", "description": ""}, {"key": "db_host", "label": "db_host", "type": "string", "value": "127.0.0.1", "default": "127.0.0.1", "description": ""}, {"key": "password", "label": "password", "type": "string", "value": "password", "default": "password", "description": ""}, {"key": "secured", "label": "secured", "type": "string", "value": "false", "default": "false", "description": ""}]}, "position": {"x": 459, "y": -208}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": true}, {"id": "api_webhook_agent_1782762814888", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "api_webhook_agent", "label": "Base Web hook", "description": "API Webhook Agent for external system integration", "category": "2", "icon": "Cloud", "id": 9, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#7C3AED", "badge": "Node", "sub_label": null, "user_properties": {"base_path": "/docs"}, "system_properties": {"port": "", "host": "", "workers": ""}, "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "properties": {"port": "", "host": "", "workers": "", "base_path": "/docs"}, "executionStatus": "idle", "variant": "2", "subIcon": "Cloud", "model": "", "input_contract": {"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}, "output_contract": {"result": {"data": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}, "property_schema": [{"key": "base_path", "default": "/docs", "value": "/docs"}, {"key": "port", "default": "", "value": ""}, {"key": "host", "default": "", "value": ""}, {"key": "workers", "default": "", "value": ""}], "propertySchema": [{"key": "base_path", "default": "/docs", "value": "/docs"}, {"key": "port", "default": "", "value": ""}, {"key": "host", "default": "", "value": ""}, {"key": "workers", "default": "", "value": ""}]}, "position": {"x": 34.5, "y": -208}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "profanity_guard_1782991097568", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "profanity_guard", "label": "Profanity Guard", "description": "Profanity and offensive content detection", "category": "2", "icon": "bot", "id": 6, "node_type": "NODE", "version": "1.1.0", "group": null, "color": "#ffb700", "badge": "Node", "sub_label": null, "user_properties": {}, "system_properties": {}, "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "executionStatus": "idle", "variant": "2", "subIcon": "bot", "model": "", "input_contract": {"version": "1.0", "rules": [{"field_name": "id", "field_type": "string", "required": true, "min_length": 1, "max_length": 20, "redact": true}], "additional_fields": true}, "output_contract": {}, "properties": {}, "property_schema": [], "propertySchema": []}, "position": {"x": 427.75, "y": -360.5}, "measured": {"width": 210, "height": 56}, "dragging": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "api_webhook_agent_1782762814888", "sourceHandle": "source-right", "target": "generic_mysql_query_executor_1782762522453", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__api_webhook_agent_1782762814888source-right-generic_mysql_query_executor_1782762522453target-left"}, {"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "api_webhook_agent_1782762814888", "sourceHandle": "source-right", "target": "profanity_guard_1782991097568", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__api_webhook_agent_1782762814888source-right-profanity_guard_1782991097568target-left"}], "entry_point": "input_guard"}','2026-07-07T11:05:57.811160',1,'1','2',1);
INSERT INTO workflows VALUES('test-props-workflow-1783759458','User Props Test Workflow 1783759458','',1,NULL,'testing',NULL,'{"nodes": [{"id": "guard-node-1", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "unified_content_guard", "label": "Acme Content Guard", "properties": {}}}], "edges": [], "entry_point": "input_guard"}','2026-07-11T08:44:18.153818',1,'9','12355',1);
CREATE TABLE IF NOT EXISTS "customers" (
    id INTEGER NOT NULL,
    name VARCHAR,
    domain VARCHAR,
    status VARCHAR,
    icon VARCHAR,
    color_schema VARCHAR,
    dateadded VARCHAR not null default CURRENT_TIMESTAMP,
    dateupdated VARCHAR not null default CURRENT_TIMESTAMP, custom_plugins_enabled BOOLEAN DEFAULT 0, plugin_storage_path VARCHAR, email VARCHAR, address VARCHAR, contact_person VARCHAR,
    PRIMARY KEY (id)
);
INSERT INTO customers VALUES(0,'Gateway','gateway.com','active','Building','#ff00ac','2026-06-27T16:51:43.911085','2026-07-11T07:23:18.796887',0,NULL,NULL,NULL,NULL);
INSERT INTO customers VALUES(1,'midasminds','midasminds','active','Building','#2563eb','2026-06-27T16:51:43.911085','2026-07-11T09:36:30.737157',1,'/Users/vivekjain/projects/enterprise-llm-gateway/temp/plugins',NULL,NULL,NULL);
INSERT INTO customers VALUES(2,'Acme Expected Output Test 1783754591','acme-eo-1783754591.com','active',NULL,NULL,'2026-07-11T07:23:11.942692','2026-07-11T07:23:11.942696',0,NULL,NULL,NULL,NULL);
INSERT INTO customers VALUES(5,'Acme Corp Properties Test 1783754596','acmeprops-1783754596.com','active',NULL,NULL,'2026-07-11T07:23:16.066370','2026-07-11T07:23:16.066373',0,NULL,NULL,NULL,NULL);
INSERT INTO customers VALUES(6,'Acme Expected Output Test 1783759454','acme-eo-1783759454.com','active',NULL,NULL,'2026-07-11T08:44:14.130996','2026-07-11T08:44:14.131000',0,NULL,NULL,NULL,NULL);
INSERT INTO customers VALUES(7,'Log Acme Corp','logacme.com','active',NULL,NULL,'2026-07-11T08:44:18.022388','2026-07-11T08:44:18.022392',0,NULL,NULL,NULL,NULL);
INSERT INTO customers VALUES(8,'Log Globex','logglobex.com','active',NULL,NULL,'2026-07-11T08:44:18.037620','2026-07-11T08:44:18.037623',0,NULL,NULL,NULL,NULL);
INSERT INTO customers VALUES(9,'Acme Corp Properties Test 1783759458','acmeprops-1783759458.com','active',NULL,NULL,'2026-07-11T08:44:18.140584','2026-07-11T08:44:18.140587',0,NULL,NULL,NULL,NULL);
CREATE TABLE IF NOT EXISTS "customer_nodes" (
    id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    node_name VARCHAR NOT NULL,
    properties JSON,
    is_enabled BOOLEAN DEFAULT 1,
    input_contract JSON,
    output_contract JSON,
    updated_at VARCHAR,
    label VARCHAR,
    PRIMARY KEY (id),
    FOREIGN KEY (customer_id) REFERENCES customers (id) FOREIGN KEY (node_name) REFERENCES nodes (name)
);
INSERT INTO customer_nodes VALUES(1,1,'database_node','{}',1,'{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": false}, {"field_name": "data.p", "field_type": "integer", "required": false}, {"field_name": "auth_token", "field_type": "string", "required": false}, {"field_name": "source_system", "field_type": "string", "required": false}], "additional_fields": true}','{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": false}, {"field_name": "data.chunks", "field_type": "array", "required": false, "items": {"field_type": "string"}}, {"field_name": "data.chunk_count", "field_type": "integer", "required": false}, {"field_name": "data.strategy", "field_type": "string", "required": false}, {"field_name": "data.chunk_size", "field_type": "integer", "required": false}, {"field_name": "data.chunk_overlap", "field_type": "integer", "required": false}, {"field_name": "auth_token", "field_type": "string", "required": false}, {"field_name": "source_system", "field_type": "string", "required": false}]}','2026-07-11T07:10:44.341305','Database');
INSERT INTO customer_nodes VALUES(2,1,'context_setter','{"key": "test2411", "label": "test", "type": "string", "default": "1"}',1,NULL,NULL,'2026-07-11T07:10:44.349757',NULL);
INSERT INTO customer_nodes VALUES(3,1,'custom_rule_guard','{"test": "test"}',1,NULL,NULL,'2026-07-11T07:10:44.350450',NULL);
INSERT INTO customer_nodes VALUES(4,1,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T07:10:44.351171',NULL);
INSERT INTO customer_nodes VALUES(5,1,'output_guard','{}',1,NULL,NULL,'2026-07-11T07:10:44.351652',NULL);
INSERT INTO customer_nodes VALUES(6,1,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T07:10:44.352157',NULL);
INSERT INTO customer_nodes VALUES(7,1,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T07:10:44.352696',NULL);
INSERT INTO customer_nodes VALUES(8,1,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T07:10:44.353203',NULL);
INSERT INTO customer_nodes VALUES(9,1,'sentiment_analyzer','{"sentiment": "1", "another": "a"}',1,'{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": false}, {"field_name": "data.chunks", "field_type": "array", "required": false}, {"field_name": "data.chunk_count", "field_type": "integer", "required": false}, {"field_name": "data.strategy", "field_type": "string", "required": false}, {"field_name": "data.chunk_size", "field_type": "integer", "required": false}, {"field_name": "data.chunk_overlap", "field_type": "integer", "required": false}, {"field_name": "auth_token", "field_type": "string", "required": false}, {"field_name": "source_system", "field_type": "string", "required": false}], "additional_fields": true}','{}','2026-07-11T07:10:44.353681','Sentiment Analyzer');
INSERT INTO customer_nodes VALUES(10,1,'api_webhook_agent','{"workers": "1", "base_path": "docs"}',1,'{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}','{"result": {"data": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}','2026-07-11T07:10:44.354114','Base Web hook');
INSERT INTO customer_nodes VALUES(11,1,'external_api_node','{"url": "www.bing.com/search", "protocol": "https", "method": "GET", "auth_key": "", "path": "/search", "api_path": "", "params": "[{\"q\":\"{{message}}\"}]", "auth_type": "API_KEY", "host": "www.bing.com"}',1,'{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}','{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}','2026-07-11T07:10:44.354863',NULL);
INSERT INTO customer_nodes VALUES(12,1,'gmail_email_trigger','{"oauth": "oauth", "secret_key": "secret", "secret_value": "value", "client_id": "client", "email_id": "intuact@gmail.com"}',1,NULL,NULL,'2026-07-11T07:10:44.355367',NULL);
INSERT INTO customer_nodes VALUES(13,1,'sqlite_query_executor','{"path": "./database.db"}',0,'{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": true}, {"field_name": "data.query_type", "field_type": "string", "required": true}, {"field_name": "data.field_names", "field_type": "array", "required": false}, {"field_name": "data.field_values", "field_type": "array", "required": false}], "additional_fields": true}','{"result": "{{message}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}','2026-07-11T07:10:44.356106','SQLITE');
INSERT INTO customer_nodes VALUES(14,1,'transformer_node','{"x": "x"}',1,NULL,NULL,'2026-07-11T07:10:44.357128',NULL);
INSERT INTO customer_nodes VALUES(15,1,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T07:10:44.357721',NULL);
INSERT INTO customer_nodes VALUES(16,1,'stocks_webhook_agent','{"port": "8888", "host": "0.0.0.0", "base_path": "stocks"}',1,'{"version": "1.0", "rules": [], "additional_fields": true}','{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": false}, {"field_name": "fmt", "field_type": "string", "required": false}, {"field_name": "market", "field_type": "string", "required": false}]}','2026-07-11T07:10:44.358211',NULL);
INSERT INTO customer_nodes VALUES(17,1,'stocks_api_request_node','{"auth_key": "", "url": "eodhd.com", "protocol": "https", "method": "GET", "params": "api_token=69747bd28b3bd8.99561497&fmt=json", "auth_type": "NONE", "path": "/api/eod/{{stock_token}}", "api_path": ""}',1,'{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}, {"field_name": "fmt", "field_type": "string", "required": true}], "additional_fields": true}','{"version": "1.0", "rules": [{"field_name": "root[].date", "field_type": "phone", "required": false}, {"field_name": "root[].open", "field_type": "number", "required": false}, {"field_name": "root[].high", "field_type": "number", "required": false}, {"field_name": "root[].low", "field_type": "number", "required": false}, {"field_name": "root[].close", "field_type": "number", "required": false}, {"field_name": "root[].adjusted_close", "field_type": "number", "required": false}, {"field_name": "root[].volume", "field_type": "integer", "required": false}]}','2026-07-11T07:10:44.358689',NULL);
INSERT INTO customer_nodes VALUES(18,1,'generic_llm_vector_db','{"host": "0.0.0.0.", "port": "6333", "collection": "midas_gateway_docs", "top_k": "5", "api_key": "0", "threshold": "0.7"}',1,'{"version": "1.0", "rules": [], "additional_fields": true}','{}','2026-07-11T07:10:44.359181',NULL);
INSERT INTO customer_nodes VALUES(19,1,'generic_mysql_query_executor','{"db_port": "3306", "user_name": "root", "db_host": "127.0.0.1", "password": "password", "secured": "false", "database": "test", "table": "temp", "query_type": "insert,delete,update,select"}',1,'{"version": "1.0", "rules": [{"field_name": "fields", "field_type": "object", "required": true}, {"field_name": "field_names", "field_type": "array", "required": true}, {"field_name": "field_values", "field_type": "array", "required": true}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": true}','{"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": "False"}, {"field_name": "lastrowid", "field_type": "integer", "required": "False"}], "additional_fields": "True"}','2026-07-11T07:10:44.359706','MySQL Node');
INSERT INTO customer_nodes VALUES(20,1,'qdrant_webhook_node','{"base_path": "qdrant"}',1,NULL,NULL,'2026-07-11T07:10:44.360193',NULL);
INSERT INTO customer_nodes VALUES(21,1,'text_chunker_node','{"chunking_strategy": "recursive", "chunk_size": 1000, "chunk_overlap": 200, "text": ""}',1,NULL,NULL,'2026-07-11T07:10:44.360701',NULL);
INSERT INTO customer_nodes VALUES(22,0,'generic_llm_vector_db','{"protocol": "", "method": "", "params": "", "auth_type": "", "path": ""}',1,'{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}','{}','2026-06-29T12:24:12.039229',NULL);
INSERT INTO customer_nodes VALUES(71,1,'db_webhook_agent','{"base_path": "db"}',1,'{"version": "1.0", "rules": [], "additional_fields": true}','{}','2026-07-11T07:10:44.361255','Database Webhook Node');
INSERT INTO customer_nodes VALUES(122,1,'dummy_test_node','{}',0,NULL,NULL,'2026-07-09T17:58:48.444708',NULL);
INSERT INTO customer_nodes VALUES(123,1,'dummy_source_node','{}',0,NULL,NULL,'2026-07-09T17:58:48.450385',NULL);
INSERT INTO customer_nodes VALUES(124,1,'dummy_target_node','{}',0,NULL,NULL,'2026-07-09T17:58:48.450933',NULL);
INSERT INTO customer_nodes VALUES(125,1,'unified_content_guard','{"profanity_words_system": "fuck, shit, asshole, bitch, cunt, bastard", "sensitive_keywords_system": "confidential, internal-only, secret", "enable_profanity": true, "enable_custom_keywords": true, "pii_entities": "PHONE_NUMBER, EMAIL_ADDRESS, PERSON, CREDIT_CARD", "score_threshold": 0.6, "additional_profanity_words": "", "additional_sensitive_keywords": "", "filter_mode": "all", "target_fields": "field1, field2", "enable_pii": true}',1,'{"version": "1.0", "rules": [], "additional_fields": true}','{}','2026-07-11T07:10:44.361797','Unified Content Guard');
INSERT INTO customer_nodes VALUES(2150,1,'contract_dummy_target_node','{}',0,NULL,NULL,'2026-07-09T17:58:48.446326',NULL);
INSERT INTO customer_nodes VALUES(2151,1,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T07:10:44.362206',NULL);
INSERT INTO customer_nodes VALUES(2152,2,'database_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945543',NULL);
INSERT INTO customer_nodes VALUES(2153,2,'context_setter','{}',1,NULL,NULL,'2026-07-11T07:23:11.945547',NULL);
INSERT INTO customer_nodes VALUES(2154,2,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T07:23:11.945549',NULL);
INSERT INTO customer_nodes VALUES(2155,2,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T07:23:11.945550',NULL);
INSERT INTO customer_nodes VALUES(2156,2,'output_guard','{}',1,NULL,NULL,'2026-07-11T07:23:11.945552',NULL);
INSERT INTO customer_nodes VALUES(2157,2,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T07:23:11.945553',NULL);
INSERT INTO customer_nodes VALUES(2158,2,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T07:23:11.945555',NULL);
INSERT INTO customer_nodes VALUES(2159,2,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T07:23:11.945558',NULL);
INSERT INTO customer_nodes VALUES(2160,2,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T07:23:11.945560',NULL);
INSERT INTO customer_nodes VALUES(2161,2,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:23:11.945561',NULL);
INSERT INTO customer_nodes VALUES(2162,2,'external_api_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945563',NULL);
INSERT INTO customer_nodes VALUES(2163,2,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T07:23:11.945564',NULL);
INSERT INTO customer_nodes VALUES(2164,2,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T07:23:11.945566',NULL);
INSERT INTO customer_nodes VALUES(2165,2,'transformer_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945567',NULL);
INSERT INTO customer_nodes VALUES(2166,2,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T07:23:11.945569',NULL);
INSERT INTO customer_nodes VALUES(2167,2,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:23:11.945570',NULL);
INSERT INTO customer_nodes VALUES(2168,2,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945572',NULL);
INSERT INTO customer_nodes VALUES(2169,2,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T07:23:11.945573',NULL);
INSERT INTO customer_nodes VALUES(2170,2,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T07:23:11.945575',NULL);
INSERT INTO customer_nodes VALUES(2171,2,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945577',NULL);
INSERT INTO customer_nodes VALUES(2172,2,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945579',NULL);
INSERT INTO customer_nodes VALUES(2173,2,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:23:11.945580',NULL);
INSERT INTO customer_nodes VALUES(2174,2,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T07:23:11.945582',NULL);
INSERT INTO customer_nodes VALUES(2175,2,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945583',NULL);
INSERT INTO customer_nodes VALUES(2176,2,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945585',NULL);
INSERT INTO customer_nodes VALUES(2177,2,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945586',NULL);
INSERT INTO customer_nodes VALUES(2178,2,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945588',NULL);
INSERT INTO customer_nodes VALUES(2179,2,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T07:23:11.945589',NULL);
INSERT INTO customer_nodes VALUES(2236,5,'database_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068890',NULL);
INSERT INTO customer_nodes VALUES(2237,5,'context_setter','{}',1,NULL,NULL,'2026-07-11T07:23:16.068894',NULL);
INSERT INTO customer_nodes VALUES(2238,5,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T07:23:16.068895',NULL);
INSERT INTO customer_nodes VALUES(2239,5,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T07:23:16.068897',NULL);
INSERT INTO customer_nodes VALUES(2240,5,'output_guard','{}',1,NULL,NULL,'2026-07-11T07:23:16.068898',NULL);
INSERT INTO customer_nodes VALUES(2241,5,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T07:23:16.068900',NULL);
INSERT INTO customer_nodes VALUES(2242,5,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T07:23:16.068901',NULL);
INSERT INTO customer_nodes VALUES(2243,5,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T07:23:16.068903',NULL);
INSERT INTO customer_nodes VALUES(2244,5,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T07:23:16.068904',NULL);
INSERT INTO customer_nodes VALUES(2245,5,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:23:16.068906',NULL);
INSERT INTO customer_nodes VALUES(2246,5,'external_api_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068907',NULL);
INSERT INTO customer_nodes VALUES(2247,5,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T07:23:16.068909',NULL);
INSERT INTO customer_nodes VALUES(2248,5,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T07:23:16.068910',NULL);
INSERT INTO customer_nodes VALUES(2249,5,'transformer_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068911',NULL);
INSERT INTO customer_nodes VALUES(2250,5,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T07:23:16.068913',NULL);
INSERT INTO customer_nodes VALUES(2251,5,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:23:16.068914',NULL);
INSERT INTO customer_nodes VALUES(2252,5,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068915',NULL);
INSERT INTO customer_nodes VALUES(2253,5,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T07:23:16.068917',NULL);
INSERT INTO customer_nodes VALUES(2254,5,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T07:23:16.068918',NULL);
INSERT INTO customer_nodes VALUES(2255,5,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068919',NULL);
INSERT INTO customer_nodes VALUES(2256,5,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068921',NULL);
INSERT INTO customer_nodes VALUES(2257,5,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:23:16.068922',NULL);
INSERT INTO customer_nodes VALUES(2258,5,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T07:23:16.068923',NULL);
INSERT INTO customer_nodes VALUES(2259,5,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068925',NULL);
INSERT INTO customer_nodes VALUES(2260,5,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068927',NULL);
INSERT INTO customer_nodes VALUES(2261,5,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068928',NULL);
INSERT INTO customer_nodes VALUES(2262,5,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068929',NULL);
INSERT INTO customer_nodes VALUES(2263,5,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T07:23:16.068931',NULL);
INSERT INTO customer_nodes VALUES(2264,6,'database_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195558',NULL);
INSERT INTO customer_nodes VALUES(2265,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T07:30:33.195562',NULL);
INSERT INTO customer_nodes VALUES(2266,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T07:30:33.195564',NULL);
INSERT INTO customer_nodes VALUES(2267,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T07:30:33.195566',NULL);
INSERT INTO customer_nodes VALUES(2268,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T07:30:33.195567',NULL);
INSERT INTO customer_nodes VALUES(2269,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T07:30:33.195569',NULL);
INSERT INTO customer_nodes VALUES(2270,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T07:30:33.195571',NULL);
INSERT INTO customer_nodes VALUES(2271,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T07:30:33.195572',NULL);
INSERT INTO customer_nodes VALUES(2272,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T07:30:33.195574',NULL);
INSERT INTO customer_nodes VALUES(2273,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:30:33.195575',NULL);
INSERT INTO customer_nodes VALUES(2274,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195577',NULL);
INSERT INTO customer_nodes VALUES(2275,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T07:30:33.195578',NULL);
INSERT INTO customer_nodes VALUES(2276,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T07:30:33.195580',NULL);
INSERT INTO customer_nodes VALUES(2277,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195581',NULL);
INSERT INTO customer_nodes VALUES(2278,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T07:30:33.195583',NULL);
INSERT INTO customer_nodes VALUES(2279,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:30:33.195584',NULL);
INSERT INTO customer_nodes VALUES(2280,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195586',NULL);
INSERT INTO customer_nodes VALUES(2281,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T07:30:33.195587',NULL);
INSERT INTO customer_nodes VALUES(2282,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T07:30:33.195588',NULL);
INSERT INTO customer_nodes VALUES(2283,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195590',NULL);
INSERT INTO customer_nodes VALUES(2284,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195591',NULL);
INSERT INTO customer_nodes VALUES(2285,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T07:30:33.195593',NULL);
INSERT INTO customer_nodes VALUES(2286,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T07:30:33.195594',NULL);
INSERT INTO customer_nodes VALUES(2287,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195596',NULL);
INSERT INTO customer_nodes VALUES(2288,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195597',NULL);
INSERT INTO customer_nodes VALUES(2289,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195599',NULL);
INSERT INTO customer_nodes VALUES(2290,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195600',NULL);
INSERT INTO customer_nodes VALUES(2291,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T07:30:33.195601',NULL);
INSERT INTO customer_nodes VALUES(2292,6,'database_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567698',NULL);
INSERT INTO customer_nodes VALUES(2293,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:43:52.567702',NULL);
INSERT INTO customer_nodes VALUES(2294,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.567706',NULL);
INSERT INTO customer_nodes VALUES(2295,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.567708',NULL);
INSERT INTO customer_nodes VALUES(2296,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.567709',NULL);
INSERT INTO customer_nodes VALUES(2297,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.567711',NULL);
INSERT INTO customer_nodes VALUES(2298,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.567712',NULL);
INSERT INTO customer_nodes VALUES(2299,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.567714',NULL);
INSERT INTO customer_nodes VALUES(2300,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:43:52.567715',NULL);
INSERT INTO customer_nodes VALUES(2301,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.567717',NULL);
INSERT INTO customer_nodes VALUES(2302,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567718',NULL);
INSERT INTO customer_nodes VALUES(2303,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:43:52.567720',NULL);
INSERT INTO customer_nodes VALUES(2304,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:43:52.567721',NULL);
INSERT INTO customer_nodes VALUES(2305,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567723',NULL);
INSERT INTO customer_nodes VALUES(2306,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:43:52.567724',NULL);
INSERT INTO customer_nodes VALUES(2307,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.567726',NULL);
INSERT INTO customer_nodes VALUES(2308,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567727',NULL);
INSERT INTO customer_nodes VALUES(2309,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:43:52.567729',NULL);
INSERT INTO customer_nodes VALUES(2310,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:43:52.567730',NULL);
INSERT INTO customer_nodes VALUES(2311,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567731',NULL);
INSERT INTO customer_nodes VALUES(2312,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567733',NULL);
INSERT INTO customer_nodes VALUES(2313,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.567734',NULL);
INSERT INTO customer_nodes VALUES(2314,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.567736',NULL);
INSERT INTO customer_nodes VALUES(2315,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567737',NULL);
INSERT INTO customer_nodes VALUES(2316,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567739',NULL);
INSERT INTO customer_nodes VALUES(2317,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567740',NULL);
INSERT INTO customer_nodes VALUES(2318,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567741',NULL);
INSERT INTO customer_nodes VALUES(2319,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.567743',NULL);
INSERT INTO customer_nodes VALUES(2320,6,'database_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586927',NULL);
INSERT INTO customer_nodes VALUES(2321,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:43:52.586930',NULL);
INSERT INTO customer_nodes VALUES(2322,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.586932',NULL);
INSERT INTO customer_nodes VALUES(2323,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.586933',NULL);
INSERT INTO customer_nodes VALUES(2324,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.586935',NULL);
INSERT INTO customer_nodes VALUES(2325,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.586936',NULL);
INSERT INTO customer_nodes VALUES(2326,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.586937',NULL);
INSERT INTO customer_nodes VALUES(2327,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.586940',NULL);
INSERT INTO customer_nodes VALUES(2328,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:43:52.586942',NULL);
INSERT INTO customer_nodes VALUES(2329,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.586943',NULL);
INSERT INTO customer_nodes VALUES(2330,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586945',NULL);
INSERT INTO customer_nodes VALUES(2331,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:43:52.586946',NULL);
INSERT INTO customer_nodes VALUES(2332,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:43:52.586947',NULL);
INSERT INTO customer_nodes VALUES(2333,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586949',NULL);
INSERT INTO customer_nodes VALUES(2334,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:43:52.586950',NULL);
INSERT INTO customer_nodes VALUES(2335,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.586951',NULL);
INSERT INTO customer_nodes VALUES(2336,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586953',NULL);
INSERT INTO customer_nodes VALUES(2337,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:43:52.586954',NULL);
INSERT INTO customer_nodes VALUES(2338,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:43:52.586956',NULL);
INSERT INTO customer_nodes VALUES(2339,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586957',NULL);
INSERT INTO customer_nodes VALUES(2340,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586958',NULL);
INSERT INTO customer_nodes VALUES(2341,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:43:52.586960',NULL);
INSERT INTO customer_nodes VALUES(2342,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:43:52.586961',NULL);
INSERT INTO customer_nodes VALUES(2343,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586963',NULL);
INSERT INTO customer_nodes VALUES(2344,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586964',NULL);
INSERT INTO customer_nodes VALUES(2345,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586966',NULL);
INSERT INTO customer_nodes VALUES(2346,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586967',NULL);
INSERT INTO customer_nodes VALUES(2347,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:43:52.586968',NULL);
INSERT INTO customer_nodes VALUES(2348,6,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641909',NULL);
INSERT INTO customer_nodes VALUES(2349,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:08.641914',NULL);
INSERT INTO customer_nodes VALUES(2350,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.641917',NULL);
INSERT INTO customer_nodes VALUES(2351,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.641918',NULL);
INSERT INTO customer_nodes VALUES(2352,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.641920',NULL);
INSERT INTO customer_nodes VALUES(2353,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.641921',NULL);
INSERT INTO customer_nodes VALUES(2354,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.641922',NULL);
INSERT INTO customer_nodes VALUES(2355,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.641924',NULL);
INSERT INTO customer_nodes VALUES(2356,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:08.641925',NULL);
INSERT INTO customer_nodes VALUES(2357,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.641927',NULL);
INSERT INTO customer_nodes VALUES(2358,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641928',NULL);
INSERT INTO customer_nodes VALUES(2359,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:08.641929',NULL);
INSERT INTO customer_nodes VALUES(2360,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:08.641931',NULL);
INSERT INTO customer_nodes VALUES(2361,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641932',NULL);
INSERT INTO customer_nodes VALUES(2362,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:08.641933',NULL);
INSERT INTO customer_nodes VALUES(2363,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.641935',NULL);
INSERT INTO customer_nodes VALUES(2364,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641936',NULL);
INSERT INTO customer_nodes VALUES(2365,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:08.641937',NULL);
INSERT INTO customer_nodes VALUES(2366,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:08.641939',NULL);
INSERT INTO customer_nodes VALUES(2367,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641940',NULL);
INSERT INTO customer_nodes VALUES(2368,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641941',NULL);
INSERT INTO customer_nodes VALUES(2369,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.641943',NULL);
INSERT INTO customer_nodes VALUES(2370,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.641944',NULL);
INSERT INTO customer_nodes VALUES(2371,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641945',NULL);
INSERT INTO customer_nodes VALUES(2372,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641947',NULL);
INSERT INTO customer_nodes VALUES(2373,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641948',NULL);
INSERT INTO customer_nodes VALUES(2374,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641949',NULL);
INSERT INTO customer_nodes VALUES(2375,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.641950',NULL);
INSERT INTO customer_nodes VALUES(2376,6,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658184',NULL);
INSERT INTO customer_nodes VALUES(2377,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:08.658186',NULL);
INSERT INTO customer_nodes VALUES(2378,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.658188',NULL);
INSERT INTO customer_nodes VALUES(2379,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.658190',NULL);
INSERT INTO customer_nodes VALUES(2380,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.658191',NULL);
INSERT INTO customer_nodes VALUES(2381,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.658193',NULL);
INSERT INTO customer_nodes VALUES(2382,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.658194',NULL);
INSERT INTO customer_nodes VALUES(2383,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.658196',NULL);
INSERT INTO customer_nodes VALUES(2384,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:08.658197',NULL);
INSERT INTO customer_nodes VALUES(2385,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.658199',NULL);
INSERT INTO customer_nodes VALUES(2386,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658200',NULL);
INSERT INTO customer_nodes VALUES(2387,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:08.658201',NULL);
INSERT INTO customer_nodes VALUES(2388,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:08.658203',NULL);
INSERT INTO customer_nodes VALUES(2389,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658204',NULL);
INSERT INTO customer_nodes VALUES(2390,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:08.658206',NULL);
INSERT INTO customer_nodes VALUES(2391,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.658207',NULL);
INSERT INTO customer_nodes VALUES(2392,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658209',NULL);
INSERT INTO customer_nodes VALUES(2393,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:08.658210',NULL);
INSERT INTO customer_nodes VALUES(2394,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:08.658212',NULL);
INSERT INTO customer_nodes VALUES(2395,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658213',NULL);
INSERT INTO customer_nodes VALUES(2396,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658214',NULL);
INSERT INTO customer_nodes VALUES(2397,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:08.658216',NULL);
INSERT INTO customer_nodes VALUES(2398,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:08.658217',NULL);
INSERT INTO customer_nodes VALUES(2399,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658219',NULL);
INSERT INTO customer_nodes VALUES(2400,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658220',NULL);
INSERT INTO customer_nodes VALUES(2401,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658222',NULL);
INSERT INTO customer_nodes VALUES(2402,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658223',NULL);
INSERT INTO customer_nodes VALUES(2403,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.658224',NULL);
INSERT INTO customer_nodes VALUES(2404,6,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:08.678372',NULL);
INSERT INTO customer_nodes VALUES(2405,6,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009111',NULL);
INSERT INTO customer_nodes VALUES(2406,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:14.009115',NULL);
INSERT INTO customer_nodes VALUES(2407,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.009117',NULL);
INSERT INTO customer_nodes VALUES(2408,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.009119',NULL);
INSERT INTO customer_nodes VALUES(2409,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.009120',NULL);
INSERT INTO customer_nodes VALUES(2410,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.009122',NULL);
INSERT INTO customer_nodes VALUES(2411,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.009123',NULL);
INSERT INTO customer_nodes VALUES(2412,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.009125',NULL);
INSERT INTO customer_nodes VALUES(2413,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:14.009126',NULL);
INSERT INTO customer_nodes VALUES(2414,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.009128',NULL);
INSERT INTO customer_nodes VALUES(2415,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009129',NULL);
INSERT INTO customer_nodes VALUES(2416,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:14.009131',NULL);
INSERT INTO customer_nodes VALUES(2417,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:14.009132',NULL);
INSERT INTO customer_nodes VALUES(2418,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009133',NULL);
INSERT INTO customer_nodes VALUES(2419,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:14.009135',NULL);
INSERT INTO customer_nodes VALUES(2420,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.009136',NULL);
INSERT INTO customer_nodes VALUES(2421,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009138',NULL);
INSERT INTO customer_nodes VALUES(2422,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:14.009139',NULL);
INSERT INTO customer_nodes VALUES(2423,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:14.009141',NULL);
INSERT INTO customer_nodes VALUES(2424,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009142',NULL);
INSERT INTO customer_nodes VALUES(2425,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009143',NULL);
INSERT INTO customer_nodes VALUES(2426,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.009145',NULL);
INSERT INTO customer_nodes VALUES(2427,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.009146',NULL);
INSERT INTO customer_nodes VALUES(2428,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009148',NULL);
INSERT INTO customer_nodes VALUES(2429,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009150',NULL);
INSERT INTO customer_nodes VALUES(2430,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009152',NULL);
INSERT INTO customer_nodes VALUES(2431,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009154',NULL);
INSERT INTO customer_nodes VALUES(2432,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009156',NULL);
INSERT INTO customer_nodes VALUES(2433,6,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.009157',NULL);
INSERT INTO customer_nodes VALUES(2434,6,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027251',NULL);
INSERT INTO customer_nodes VALUES(2435,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:14.027254',NULL);
INSERT INTO customer_nodes VALUES(2436,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.027256',NULL);
INSERT INTO customer_nodes VALUES(2437,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.027258',NULL);
INSERT INTO customer_nodes VALUES(2438,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.027259',NULL);
INSERT INTO customer_nodes VALUES(2439,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.027261',NULL);
INSERT INTO customer_nodes VALUES(2440,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.027262',NULL);
INSERT INTO customer_nodes VALUES(2441,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.027264',NULL);
INSERT INTO customer_nodes VALUES(2442,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:14.027265',NULL);
INSERT INTO customer_nodes VALUES(2443,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.027267',NULL);
INSERT INTO customer_nodes VALUES(2444,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027268',NULL);
INSERT INTO customer_nodes VALUES(2445,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:14.027270',NULL);
INSERT INTO customer_nodes VALUES(2446,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:14.027271',NULL);
INSERT INTO customer_nodes VALUES(2447,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027273',NULL);
INSERT INTO customer_nodes VALUES(2448,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:14.027274',NULL);
INSERT INTO customer_nodes VALUES(2449,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.027276',NULL);
INSERT INTO customer_nodes VALUES(2450,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027277',NULL);
INSERT INTO customer_nodes VALUES(2451,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:14.027279',NULL);
INSERT INTO customer_nodes VALUES(2452,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:14.027282',NULL);
INSERT INTO customer_nodes VALUES(2453,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027283',NULL);
INSERT INTO customer_nodes VALUES(2454,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027285',NULL);
INSERT INTO customer_nodes VALUES(2455,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.027286',NULL);
INSERT INTO customer_nodes VALUES(2456,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.027288',NULL);
INSERT INTO customer_nodes VALUES(2457,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027290',NULL);
INSERT INTO customer_nodes VALUES(2458,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027291',NULL);
INSERT INTO customer_nodes VALUES(2459,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027292',NULL);
INSERT INTO customer_nodes VALUES(2460,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027294',NULL);
INSERT INTO customer_nodes VALUES(2461,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027295',NULL);
INSERT INTO customer_nodes VALUES(2462,6,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.027297',NULL);
INSERT INTO customer_nodes VALUES(2463,6,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133436',NULL);
INSERT INTO customer_nodes VALUES(2464,6,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:14.133440',NULL);
INSERT INTO customer_nodes VALUES(2465,6,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.133442',NULL);
INSERT INTO customer_nodes VALUES(2466,6,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.133443',NULL);
INSERT INTO customer_nodes VALUES(2467,6,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.133444',NULL);
INSERT INTO customer_nodes VALUES(2468,6,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.133446',NULL);
INSERT INTO customer_nodes VALUES(2469,6,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.133455',NULL);
INSERT INTO customer_nodes VALUES(2470,6,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.133456',NULL);
INSERT INTO customer_nodes VALUES(2471,6,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:14.133459',NULL);
INSERT INTO customer_nodes VALUES(2472,6,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.133460',NULL);
INSERT INTO customer_nodes VALUES(2473,6,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133462',NULL);
INSERT INTO customer_nodes VALUES(2474,6,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:14.133463',NULL);
INSERT INTO customer_nodes VALUES(2475,6,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:14.133464',NULL);
INSERT INTO customer_nodes VALUES(2476,6,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133465',NULL);
INSERT INTO customer_nodes VALUES(2477,6,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:14.133467',NULL);
INSERT INTO customer_nodes VALUES(2478,6,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.133468',NULL);
INSERT INTO customer_nodes VALUES(2479,6,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133469',NULL);
INSERT INTO customer_nodes VALUES(2480,6,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:14.133470',NULL);
INSERT INTO customer_nodes VALUES(2481,6,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:14.133472',NULL);
INSERT INTO customer_nodes VALUES(2482,6,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133473',NULL);
INSERT INTO customer_nodes VALUES(2483,6,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133475',NULL);
INSERT INTO customer_nodes VALUES(2484,6,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:14.133476',NULL);
INSERT INTO customer_nodes VALUES(2485,6,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:14.133477',NULL);
INSERT INTO customer_nodes VALUES(2486,6,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133478',NULL);
INSERT INTO customer_nodes VALUES(2487,6,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133480',NULL);
INSERT INTO customer_nodes VALUES(2488,6,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133481',NULL);
INSERT INTO customer_nodes VALUES(2489,6,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133482',NULL);
INSERT INTO customer_nodes VALUES(2490,6,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133483',NULL);
INSERT INTO customer_nodes VALUES(2491,6,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:14.133485',NULL);
INSERT INTO customer_nodes VALUES(2492,7,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024377',NULL);
INSERT INTO customer_nodes VALUES(2493,7,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:18.024380',NULL);
INSERT INTO customer_nodes VALUES(2494,7,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.024382',NULL);
INSERT INTO customer_nodes VALUES(2495,7,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.024383',NULL);
INSERT INTO customer_nodes VALUES(2496,7,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.024384',NULL);
INSERT INTO customer_nodes VALUES(2497,7,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.024386',NULL);
INSERT INTO customer_nodes VALUES(2498,7,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.024387',NULL);
INSERT INTO customer_nodes VALUES(2499,7,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.024388',NULL);
INSERT INTO customer_nodes VALUES(2500,7,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:18.024390',NULL);
INSERT INTO customer_nodes VALUES(2501,7,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.024391',NULL);
INSERT INTO customer_nodes VALUES(2502,7,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024393',NULL);
INSERT INTO customer_nodes VALUES(2503,7,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:18.024394',NULL);
INSERT INTO customer_nodes VALUES(2504,7,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:18.024395',NULL);
INSERT INTO customer_nodes VALUES(2505,7,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024396',NULL);
INSERT INTO customer_nodes VALUES(2506,7,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:18.024398',NULL);
INSERT INTO customer_nodes VALUES(2507,7,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.024399',NULL);
INSERT INTO customer_nodes VALUES(2508,7,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024400',NULL);
INSERT INTO customer_nodes VALUES(2509,7,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:18.024412',NULL);
INSERT INTO customer_nodes VALUES(2510,7,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:18.024413',NULL);
INSERT INTO customer_nodes VALUES(2511,7,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024414',NULL);
INSERT INTO customer_nodes VALUES(2512,7,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024416',NULL);
INSERT INTO customer_nodes VALUES(2513,7,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.024417',NULL);
INSERT INTO customer_nodes VALUES(2514,7,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.024419',NULL);
INSERT INTO customer_nodes VALUES(2515,7,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024420',NULL);
INSERT INTO customer_nodes VALUES(2516,7,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024421',NULL);
INSERT INTO customer_nodes VALUES(2517,7,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024422',NULL);
INSERT INTO customer_nodes VALUES(2518,7,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024424',NULL);
INSERT INTO customer_nodes VALUES(2519,7,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024425',NULL);
INSERT INTO customer_nodes VALUES(2520,7,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.024426',NULL);
INSERT INTO customer_nodes VALUES(2521,8,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039324',NULL);
INSERT INTO customer_nodes VALUES(2522,8,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:18.039327',NULL);
INSERT INTO customer_nodes VALUES(2523,8,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.039328',NULL);
INSERT INTO customer_nodes VALUES(2524,8,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.039330',NULL);
INSERT INTO customer_nodes VALUES(2525,8,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.039331',NULL);
INSERT INTO customer_nodes VALUES(2526,8,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.039332',NULL);
INSERT INTO customer_nodes VALUES(2527,8,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.039334',NULL);
INSERT INTO customer_nodes VALUES(2528,8,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.039335',NULL);
INSERT INTO customer_nodes VALUES(2529,8,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:18.039336',NULL);
INSERT INTO customer_nodes VALUES(2530,8,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.039337',NULL);
INSERT INTO customer_nodes VALUES(2531,8,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039339',NULL);
INSERT INTO customer_nodes VALUES(2532,8,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:18.039340',NULL);
INSERT INTO customer_nodes VALUES(2533,8,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:18.039341',NULL);
INSERT INTO customer_nodes VALUES(2534,8,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039343',NULL);
INSERT INTO customer_nodes VALUES(2535,8,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:18.039344',NULL);
INSERT INTO customer_nodes VALUES(2536,8,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.039345',NULL);
INSERT INTO customer_nodes VALUES(2537,8,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039348',NULL);
INSERT INTO customer_nodes VALUES(2538,8,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:18.039349',NULL);
INSERT INTO customer_nodes VALUES(2539,8,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:18.039350',NULL);
INSERT INTO customer_nodes VALUES(2540,8,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039353',NULL);
INSERT INTO customer_nodes VALUES(2541,8,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039354',NULL);
INSERT INTO customer_nodes VALUES(2542,8,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.039356',NULL);
INSERT INTO customer_nodes VALUES(2543,8,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.039357',NULL);
INSERT INTO customer_nodes VALUES(2544,8,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039358',NULL);
INSERT INTO customer_nodes VALUES(2545,8,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039359',NULL);
INSERT INTO customer_nodes VALUES(2546,8,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039361',NULL);
INSERT INTO customer_nodes VALUES(2547,8,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039362',NULL);
INSERT INTO customer_nodes VALUES(2548,8,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039363',NULL);
INSERT INTO customer_nodes VALUES(2549,8,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.039365',NULL);
INSERT INTO customer_nodes VALUES(2550,9,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143046',NULL);
INSERT INTO customer_nodes VALUES(2551,9,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:18.143049',NULL);
INSERT INTO customer_nodes VALUES(2552,9,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.143050',NULL);
INSERT INTO customer_nodes VALUES(2553,9,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.143052',NULL);
INSERT INTO customer_nodes VALUES(2554,9,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.143053',NULL);
INSERT INTO customer_nodes VALUES(2555,9,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.143055',NULL);
INSERT INTO customer_nodes VALUES(2556,9,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.143056',NULL);
INSERT INTO customer_nodes VALUES(2557,9,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.143058',NULL);
INSERT INTO customer_nodes VALUES(2558,9,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:18.143059',NULL);
INSERT INTO customer_nodes VALUES(2559,9,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.143060',NULL);
INSERT INTO customer_nodes VALUES(2560,9,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143062',NULL);
INSERT INTO customer_nodes VALUES(2561,9,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:18.143063',NULL);
INSERT INTO customer_nodes VALUES(2562,9,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:18.143064',NULL);
INSERT INTO customer_nodes VALUES(2563,9,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143066',NULL);
INSERT INTO customer_nodes VALUES(2564,9,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:18.143067',NULL);
INSERT INTO customer_nodes VALUES(2565,9,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.143069',NULL);
INSERT INTO customer_nodes VALUES(2566,9,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143070',NULL);
INSERT INTO customer_nodes VALUES(2567,9,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:18.143071',NULL);
INSERT INTO customer_nodes VALUES(2568,9,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:18.143073',NULL);
INSERT INTO customer_nodes VALUES(2569,9,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143074',NULL);
INSERT INTO customer_nodes VALUES(2570,9,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143075',NULL);
INSERT INTO customer_nodes VALUES(2571,9,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:18.143077',NULL);
INSERT INTO customer_nodes VALUES(2572,9,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:18.143078',NULL);
INSERT INTO customer_nodes VALUES(2573,9,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143079',NULL);
INSERT INTO customer_nodes VALUES(2574,9,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143081',NULL);
INSERT INTO customer_nodes VALUES(2575,9,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143082',NULL);
INSERT INTO customer_nodes VALUES(2576,9,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143084',NULL);
INSERT INTO customer_nodes VALUES(2577,9,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143085',NULL);
INSERT INTO customer_nodes VALUES(2578,9,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:18.143086',NULL);
INSERT INTO customer_nodes VALUES(2579,10,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582589',NULL);
INSERT INTO customer_nodes VALUES(2580,10,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:40.582597',NULL);
INSERT INTO customer_nodes VALUES(2581,10,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.582599',NULL);
INSERT INTO customer_nodes VALUES(2582,10,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.582601',NULL);
INSERT INTO customer_nodes VALUES(2583,10,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.582603',NULL);
INSERT INTO customer_nodes VALUES(2584,10,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.582604',NULL);
INSERT INTO customer_nodes VALUES(2585,10,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.582606',NULL);
INSERT INTO customer_nodes VALUES(2586,10,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.582607',NULL);
INSERT INTO customer_nodes VALUES(2587,10,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:40.582609',NULL);
INSERT INTO customer_nodes VALUES(2588,10,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.582610',NULL);
INSERT INTO customer_nodes VALUES(2589,10,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582612',NULL);
INSERT INTO customer_nodes VALUES(2590,10,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:40.582614',NULL);
INSERT INTO customer_nodes VALUES(2591,10,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:40.582615',NULL);
INSERT INTO customer_nodes VALUES(2592,10,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582616',NULL);
INSERT INTO customer_nodes VALUES(2593,10,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:40.582618',NULL);
INSERT INTO customer_nodes VALUES(2594,10,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.582619',NULL);
INSERT INTO customer_nodes VALUES(2595,10,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582621',NULL);
INSERT INTO customer_nodes VALUES(2596,10,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:40.582622',NULL);
INSERT INTO customer_nodes VALUES(2597,10,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:40.582624',NULL);
INSERT INTO customer_nodes VALUES(2598,10,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582625',NULL);
INSERT INTO customer_nodes VALUES(2599,10,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582626',NULL);
INSERT INTO customer_nodes VALUES(2600,10,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.582628',NULL);
INSERT INTO customer_nodes VALUES(2601,10,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.582629',NULL);
INSERT INTO customer_nodes VALUES(2602,10,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582631',NULL);
INSERT INTO customer_nodes VALUES(2603,10,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582632',NULL);
INSERT INTO customer_nodes VALUES(2604,10,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582634',NULL);
INSERT INTO customer_nodes VALUES(2605,10,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582635',NULL);
INSERT INTO customer_nodes VALUES(2606,10,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582636',NULL);
INSERT INTO customer_nodes VALUES(2607,10,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.582638',NULL);
INSERT INTO customer_nodes VALUES(2608,10,'database_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600617',NULL);
INSERT INTO customer_nodes VALUES(2609,10,'context_setter','{}',1,NULL,NULL,'2026-07-11T08:44:40.600621',NULL);
INSERT INTO customer_nodes VALUES(2610,10,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.600623',NULL);
INSERT INTO customer_nodes VALUES(2611,10,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.600625',NULL);
INSERT INTO customer_nodes VALUES(2612,10,'output_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.600626',NULL);
INSERT INTO customer_nodes VALUES(2613,10,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.600628',NULL);
INSERT INTO customer_nodes VALUES(2614,10,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.600629',NULL);
INSERT INTO customer_nodes VALUES(2615,10,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.600631',NULL);
INSERT INTO customer_nodes VALUES(2616,10,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T08:44:40.600632',NULL);
INSERT INTO customer_nodes VALUES(2617,10,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.600634',NULL);
INSERT INTO customer_nodes VALUES(2618,10,'external_api_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600635',NULL);
INSERT INTO customer_nodes VALUES(2619,10,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:40.600637',NULL);
INSERT INTO customer_nodes VALUES(2620,10,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:40.600638',NULL);
INSERT INTO customer_nodes VALUES(2621,10,'transformer_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600639',NULL);
INSERT INTO customer_nodes VALUES(2622,10,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T08:44:40.600641',NULL);
INSERT INTO customer_nodes VALUES(2623,10,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.600642',NULL);
INSERT INTO customer_nodes VALUES(2624,10,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600644',NULL);
INSERT INTO customer_nodes VALUES(2625,10,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T08:44:40.600645',NULL);
INSERT INTO customer_nodes VALUES(2626,10,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T08:44:40.600647',NULL);
INSERT INTO customer_nodes VALUES(2627,10,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600648',NULL);
INSERT INTO customer_nodes VALUES(2628,10,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600650',NULL);
INSERT INTO customer_nodes VALUES(2629,10,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T08:44:40.600651',NULL);
INSERT INTO customer_nodes VALUES(2630,10,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T08:44:40.600653',NULL);
INSERT INTO customer_nodes VALUES(2631,10,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600654',NULL);
INSERT INTO customer_nodes VALUES(2632,10,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600656',NULL);
INSERT INTO customer_nodes VALUES(2633,10,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600657',NULL);
INSERT INTO customer_nodes VALUES(2634,10,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600659',NULL);
INSERT INTO customer_nodes VALUES(2635,10,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600660',NULL);
INSERT INTO customer_nodes VALUES(2636,10,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.600661',NULL);
INSERT INTO customer_nodes VALUES(2637,10,'client_10_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T08:44:40.629328',NULL);
INSERT INTO customer_nodes VALUES(2638,1,'client_1_sap_agent','{}',1,NULL,NULL,'2026-07-11T10:33:50.428223',NULL);
INSERT INTO customer_nodes VALUES(2639,10,'database_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501545',NULL);
INSERT INTO customer_nodes VALUES(2640,10,'context_setter','{}',1,NULL,NULL,'2026-07-11T10:33:54.501548',NULL);
INSERT INTO customer_nodes VALUES(2641,10,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.501550',NULL);
INSERT INTO customer_nodes VALUES(2642,10,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.501552',NULL);
INSERT INTO customer_nodes VALUES(2643,10,'output_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.501553',NULL);
INSERT INTO customer_nodes VALUES(2644,10,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.501555',NULL);
INSERT INTO customer_nodes VALUES(2645,10,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.501556',NULL);
INSERT INTO customer_nodes VALUES(2646,10,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.501557',NULL);
INSERT INTO customer_nodes VALUES(2647,10,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T10:33:54.501560',NULL);
INSERT INTO customer_nodes VALUES(2648,10,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.501561',NULL);
INSERT INTO customer_nodes VALUES(2649,10,'external_api_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501563',NULL);
INSERT INTO customer_nodes VALUES(2650,10,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T10:33:54.501564',NULL);
INSERT INTO customer_nodes VALUES(2651,10,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T10:33:54.501565',NULL);
INSERT INTO customer_nodes VALUES(2652,10,'transformer_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501567',NULL);
INSERT INTO customer_nodes VALUES(2653,10,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T10:33:54.501568',NULL);
INSERT INTO customer_nodes VALUES(2654,10,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.501569',NULL);
INSERT INTO customer_nodes VALUES(2655,10,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501570',NULL);
INSERT INTO customer_nodes VALUES(2656,10,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T10:33:54.501572',NULL);
INSERT INTO customer_nodes VALUES(2657,10,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T10:33:54.501573',NULL);
INSERT INTO customer_nodes VALUES(2658,10,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501574',NULL);
INSERT INTO customer_nodes VALUES(2659,10,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501576',NULL);
INSERT INTO customer_nodes VALUES(2660,10,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.501577',NULL);
INSERT INTO customer_nodes VALUES(2661,10,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.501579',NULL);
INSERT INTO customer_nodes VALUES(2662,10,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501581',NULL);
INSERT INTO customer_nodes VALUES(2663,10,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501582',NULL);
INSERT INTO customer_nodes VALUES(2664,10,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501583',NULL);
INSERT INTO customer_nodes VALUES(2665,10,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501585',NULL);
INSERT INTO customer_nodes VALUES(2666,10,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501586',NULL);
INSERT INTO customer_nodes VALUES(2667,10,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501587',NULL);
INSERT INTO customer_nodes VALUES(2668,10,'client_10_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.501589',NULL);
INSERT INTO customer_nodes VALUES(2669,10,'client_1_sap_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.501590',NULL);
INSERT INTO customer_nodes VALUES(2670,10,'database_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518382',NULL);
INSERT INTO customer_nodes VALUES(2671,10,'context_setter','{}',1,NULL,NULL,'2026-07-11T10:33:54.518385',NULL);
INSERT INTO customer_nodes VALUES(2672,10,'custom_rule_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.518387',NULL);
INSERT INTO customer_nodes VALUES(2673,10,'generic_llm_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.518388',NULL);
INSERT INTO customer_nodes VALUES(2674,10,'output_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.518389',NULL);
INSERT INTO customer_nodes VALUES(2675,10,'presidio_ner_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.518391',NULL);
INSERT INTO customer_nodes VALUES(2676,10,'profanity_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.518392',NULL);
INSERT INTO customer_nodes VALUES(2677,10,'scheduler_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.518393',NULL);
INSERT INTO customer_nodes VALUES(2678,10,'sentiment_analyzer','{}',1,NULL,NULL,'2026-07-11T10:33:54.518395',NULL);
INSERT INTO customer_nodes VALUES(2679,10,'api_webhook_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.518396',NULL);
INSERT INTO customer_nodes VALUES(2680,10,'external_api_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518397',NULL);
INSERT INTO customer_nodes VALUES(2681,10,'gmail_email_trigger','{}',1,NULL,NULL,'2026-07-11T10:33:54.518399',NULL);
INSERT INTO customer_nodes VALUES(2682,10,'sqlite_query_executor','{}',1,NULL,NULL,'2026-07-11T10:33:54.518400',NULL);
INSERT INTO customer_nodes VALUES(2683,10,'transformer_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518401',NULL);
INSERT INTO customer_nodes VALUES(2684,10,'outlook_email_trigger','{}',1,NULL,NULL,'2026-07-11T10:33:54.518402',NULL);
INSERT INTO customer_nodes VALUES(2685,10,'stocks_webhook_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.518404',NULL);
INSERT INTO customer_nodes VALUES(2686,10,'stocks_api_request_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518405',NULL);
INSERT INTO customer_nodes VALUES(2687,10,'generic_llm_vector_db','{}',1,NULL,NULL,'2026-07-11T10:33:54.518406',NULL);
INSERT INTO customer_nodes VALUES(2688,10,'generic_mysql_query_executor','{}',1,NULL,NULL,'2026-07-11T10:33:54.518408',NULL);
INSERT INTO customer_nodes VALUES(2689,10,'qdrant_webhook_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518409',NULL);
INSERT INTO customer_nodes VALUES(2690,10,'text_chunker_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518411',NULL);
INSERT INTO customer_nodes VALUES(2691,10,'db_webhook_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.518412',NULL);
INSERT INTO customer_nodes VALUES(2692,10,'unified_content_guard','{}',1,NULL,NULL,'2026-07-11T10:33:54.518413',NULL);
INSERT INTO customer_nodes VALUES(2693,10,'passthrough_trigger_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518415',NULL);
INSERT INTO customer_nodes VALUES(2694,10,'dummy_test_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518416',NULL);
INSERT INTO customer_nodes VALUES(2695,10,'contract_dummy_target_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518417',NULL);
INSERT INTO customer_nodes VALUES(2696,10,'dummy_source_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518419',NULL);
INSERT INTO customer_nodes VALUES(2697,10,'dummy_target_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518420',NULL);
INSERT INTO customer_nodes VALUES(2698,10,'client_6_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518421',NULL);
INSERT INTO customer_nodes VALUES(2699,10,'client_10_test_custom_startup_node','{}',1,NULL,NULL,'2026-07-11T10:33:54.518422',NULL);
INSERT INTO customer_nodes VALUES(2700,10,'client_1_sap_agent','{}',1,NULL,NULL,'2026-07-11T10:33:54.518424',NULL);
CREATE TABLE IF NOT EXISTS "nodes" (
    id INTEGER NOT NULL,
    name VARCHAR,
    label VARCHAR,
    node_type VARCHAR,
    description VARCHAR,
    version VARCHAR,
    category VARCHAR,
    "group" VARCHAR,
    icon VARCHAR,
    color VARCHAR,
    badge VARCHAR,
    sub_label VARCHAR,
    property_schema JSON,
    user_properties JSON,
    system_properties JSON,
    input_contract JSON,
    output_contract JSOM, customer_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY (category) REFERENCES categories (id)
);
INSERT INTO nodes VALUES(0,'database_node','Database','NODE','Connects to most common database ','1.0.0','5',NULL,'database','#772711',NULL,NULL,NULL,'[]','[]',0,NULL,NULL);
INSERT INTO nodes VALUES(1,'context_setter','Context Setter','NODE','Enriches input with user context from CRM / DB','1.0.0','1',NULL,'User','#7C3000','Trigger','Call any LLM','[{"key": "test2411", "label": "test", "type": "string", "default": "1"}]','[]','[{"key": "key", "default": "test2411"}, {"key": "label", "default": "test"}, {"key": "type", "default": "string"}, {"key": "default", "default": "1"}]','{"version": "1.0", "rules": [{"field_name": "user_id", "field_type": "string", "required": true, "min_length": 1, "max_length": 48}], "additional_fields": true}','{"user_id": "", "data": []}',NULL);
INSERT INTO nodes VALUES(2,'custom_rule_guard','Custom Rule','NODE','Dynamic rule-based guard using JSON config','1.0.0','2',NULL,'bot','#C01010','Node',NULL,'[]','[]','{"test": "test"}',0,NULL,NULL);
INSERT INTO nodes VALUES(3,'generic_llm_agent','LLM Agent','NODE','Calls an LLM via specific IP and Port using OpenAI-compatible API','1.0.0','1',NULL,'Brain','#17a2b8','Node','Calls any LLM at the given port with the system prompt','[]','[]','{}','{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}',NULL,NULL);
INSERT INTO nodes VALUES(4,'output_guard','Output Guard','NODE','Final safety check - PII leak, MAD, policy compliance','1.0.0','2',NULL,'bot','#7C3AED','Node',NULL,'[{"key": "checkPII", "type": "boolean", "label": "Check for PII leaks", "default": true}, {"key": "checkMAD", "type": "boolean", "label": "Check for MAD (Misogyny, Ableism, Discrimination)", "default": true}, {"key": "checkPolicy", "type": "boolean", "label": "Check for custom policy violations", "default": false}]','[]','[]','{"version": "1.0", "rules": [], "additional_fields": true}','{}',NULL);
INSERT INTO nodes VALUES(5,'presidio_ner_guard','Base Node','DEFAULT','Advanced PII + Custom Rules using Presidio','1.1.0','2','Custom','bot','#5E0CEC','Node',NULL,'[]','{}','{}','{}','{}',NULL);
INSERT INTO nodes VALUES(6,'profanity_guard','Base Node','DEFAULT','Profanity and offensive content detection','1.1.0','2','Custom','bot','#5E0CEC','Node',NULL,'[{"key": "enabled", "label": "Enabled", "type": "boolean"}, {"key": "sensitivity", "label": "Sensitivity", "type": "choice", "options": ["low", "medium", "high"]}]','{}','{}','{}','{}',NULL);
INSERT INTO nodes VALUES(7,'scheduler_agent','Scheduler','TRIGGER','Trigger scheder after n seconds','1.0.0','2',NULL,'Clock','#0000CC','Node',NULL,'[]','[]','[]','{"version": "1.0", "rules": [{"field_name": "user_id", "field_type": "json", "required": true}], "additional_fields": true}',NULL,NULL);
INSERT INTO nodes VALUES(8,'sentiment_analyzer','Sentiment Analyzer','NODE','Analyzes sentiment of user message','1.0.0','3',NULL,'bot','#12239e','Node',NULL,'[{"key": "senstivity", "label": "senstivity", "type": "string", "default": ".5"}]','[{"key": "sentiment", "default": "1"}, {"key": "another", "default": "a"}]','[{"key": "sentiment", "default": "1","description":"help"}]',0,NULL,NULL);
INSERT INTO nodes VALUES(9,'api_webhook_agent','Base Web hook','TRIGGER','API Webhook Agent for external system integration','1.0.0','2',NULL,'Cloud','#7C3AED','Node',NULL,'[]','[{"key": "base_path", "default": "/docs", "value": "docs", "label": "base_path", "type": "string", "description": ""}]','[{"key": "workers", "default": "", "value": "1", "label": "workers", "type": "number", "description": ""}]','{"version": "1.0", "rules": [], "additional_fields": true}','{"result": {"data": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}',NULL);
INSERT INTO nodes VALUES(10,'external_api_node','External API','NODE','Calls the third party API ','1.0.0','1','','Cloud','#5E0CEC','Node','','[{"key": "url", "label": "URL", "type": "string", "multiple": false, "default": "0.0.0.0"}, {"key": "path", "label": "path", "type": "string", "default": "/path"}, {"key": "api_path", "label": "api_path", "type": "string", "default": ""}, {"key": "port", "label": "port", "type": "string", "default": "80"}, {"key": "method", "label": "method", "type": "string", "default": "GET"}, {"key": "auth_token", "label": "Auth Token", "type": "string", "default": "-"}, {"key": "protocol", "label": "Protocol", "type": "string", "multiple": false, "default": "HTTP/ HTTPS"}, {"key": "auth_type", "label": "Auth Type", "type": "choice", "default": "[\"DB\",\"Auth_Token\"]"}]','[{"key": "url", "default": "www.bing.com/search"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "auth_key", "default": ""}, {"key": "path", "default": "/search"}, {"key": "api_path", "default": ""}, {"key": "params", "default": "[{\"q\":\"{{message}}\"}]"}, {"key": "auth_type", "default": "API_KEY"}]','[{"key": "host", "default": "www.bing.com"}, {"key": "auth_type", "default": "API_KEY"}]','{"version": "1.0", "rules": [], "additional_fields": true}',NULL,NULL);
INSERT INTO nodes VALUES(11,'gmail_email_trigger','Gmail','TRIGGER','Polls an IMAP server for new messages and triggers the workflow.','1.0.0','4',NULL,'mail','#EA4335',NULL,NULL,'[{"key": "auth", "label": "Auth Type", "type": "oauth"}]','[]','{"oauth": "oauth", "secret_key": "secret", "secret_value": "value", "client_id": "client", "email_id": "intuact@gmail.com"}',0,NULL,NULL);
INSERT INTO nodes VALUES(12,'sqlite_query_executor','SQLITE','NODE','Connect to SQLITE Database and execute a query','1.0.0','5','','database','#0624BA','Node','','[{"key": "query_type", "label": "username", "type": "string", "default": ""}, {"key": "field_names", "label": "Field_names", "type": "string", "default": ""}, {"key": "field_values", "label": "Field Values", "type": "string", "default": ""}]','[]','{"path": "./database.db"}','{"data":{"field_names":{"values":[],"mandatory":"True"},"field_values":{"values":[],"mandatory":"True"},"query_type":{"type":"string","mandatory":"True"}}}','{"result": "{{message}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}',NULL);
INSERT INTO nodes VALUES(13,'transformer_node','Data Transformer','NODE','Transforms input data using Jinja2 templates to match the next node''s input','1.0.0','1',NULL,'shuffle','#c9980b',NULL,NULL,'[{"key": "test", "label": "test", "type": "string", "default": ""}, {"key": "name", "label": "name", "type": "string", "default": ""}]','[]','{"x": "x"}',NULL,NULL,NULL);
INSERT INTO nodes VALUES(14,'outlook_email_trigger','Outlook OAuth Trigger','TRIGGER','Polls Outlook via Microsoft Graph API for new messages.','1.0.0','1','Custom','mail','#EA4335','Node',NULL,NULL,'[]','{}','{}','{}',NULL);
INSERT INTO nodes VALUES(17,'stocks_webhook_agent','Stocks Webhook Agent','TRIGGER','Triggers workflows on stock price movements or API alerts','1.0.0','1','Custom','bot','#2ECC71','Node',NULL,NULL,'[]','[{"key": "base_path", "default": "stocks", "label": "base_path", "type": "string", "value": "stocks", "description": "/stocks"}]','{"version": "1.0", "rules": [], "additional_fields": true}','{}',NULL);
INSERT INTO nodes VALUES(18,'stocks_api_request_node','Stocks API','NODE','Calls EODHD for stock details','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'[]','[{"key": "auth_key", "default": ""}, {"key": "url", "default": "eodhd.com"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "params", "default": "api_token=69747bd28b3bd8.99561497&fmt=json"}, {"key": "auth_type", "default": "NONE"}, {"key": "path", "default": "/api/eod/{{stock_token}}"}, {"key": "api_path", "default": ""}]','{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}','{}',NULL);
INSERT INTO nodes VALUES(19,'generic_llm_vector_db','Store data to VectorDB','NODE','Store data to VectorDB','1.0.0','10','Custom','blocks','#2cb23cff','Node',NULL,NULL,'[{"key": "host", "default": "0.0.0.0", "value": "0.0.0.0"}, {"key": "port", "default": "6333", "value": "6333"}]','{}','{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}','{}',NULL);
INSERT INTO nodes VALUES(20,'generic_mysql_query_executor','MySQL Node','NODE','Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.','1.0.0','5','Data','bot','#5E0CEC','Node',NULL,NULL,'[{"key": "database", "test": "default", "value": "test", "label": "database", "type": "string", "default": "", "description": ""}, {"key": "table", "label": "Table Name", "type": "string", "value": "temp", "default": "", "description": ""}, {"key": "query_type", "label": "Query Type ", "type": "choice", "value": "insert,delete,update,select", "default": "", "description": ""}]','[{"key": "db_port", "label": "db_port", "type": "string", "value": "3306", "default": "3306", "description": ""}, {"key": "user_name", "label": "user_name", "type": "string", "value": "root", "default": "admin", "description": ""}, {"key": "db_host", "label": "db_host", "type": "string", "value": "127.0.0.1", "default": "127.0.0.1", "description": ""}, {"key": "password", "label": "password", "type": "string", "value": "password", "default": "password", "description": ""}, {"key": "secured", "label": "secured", "type": "string", "value": "false", "default": "false", "description": ""}]','{"version": "1.0", "rules": [{"field_name": "table_name", "field_type": "string", "required": true}, {"field_name": "fields", "field_type": "object", "required": true}, {"field_name": "field_names", "field_type": "array", "required": true}, {"field_name": "field_values", "field_type": "array", "required": true}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": true}','{"version":"1.0","rules":[{"field_name":"rowcount","field_type":"integer","required":"False"},{"field_name":"lastrowid","field_type":"integer","required":"False"}],"additional_fields":"True"}',NULL);
INSERT INTO nodes VALUES(21,'qdrant_webhook_node','Qdrant Webhook Node','TRIGGER','Triggers workflows on Qdrant Vector Database events','1.0.0','1','Custom','bot','#2ECC71','Node',NULL,NULL,'[{"key": "base_path", "label": "Base Path", "type": "string", "value": "qdrant", "default": "", "description": ""}]','[]','{"version": "1.0", "rules": [], "additional_fields": true}','{}',NULL);
INSERT INTO nodes VALUES(22,'text_chunker_node','Text Chunker','NODE','Splits long text or document content into smaller overlapping chunks.','1.0.0','1','Custom','bot','#06b6d4','Node',NULL,NULL,'{"chunking_strategy": "recursive", "chunk_size": 1000, "chunk_overlap": 200, "text": ""}','{}','{}','{}',NULL);
INSERT INTO nodes VALUES(23,'db_webhook_agent','Database Webhook Node','TRIGGER','DB Webhook Agent for DB operations','1.0.0','5','Data','bot','#5E0CEC','Node',NULL,NULL,'[]','[{"key": "base_path", "default": "/docs", "value": "db", "label": "base_path", "type": "string", "description": ""}]','{"version": "1.0", "rules": [], "additional_fields": true}','{}',NULL);
INSERT INTO nodes VALUES(24,'unified_content_guard','Unified Content Guard','NODE','Unified safety node filtering PII, profanity, and custom keywords across system, tenant, and workflow scopes.','2.0.0','2','Custom','bot','#D93838','Guard',NULL,NULL,'[{"key": "enable_profanity", "label": "Enable Profanity Filtering", "type": "boolean", "default": true, "description": "Blocks offensive, inappropriate, and unsafe language."}, {"key": "enable_custom_keywords", "label": "Enable Custom Keywords", "type": "boolean", "default": true, "description": "Redacts user-defined custom keywords."}, {"key": "pii_entities", "label": "PII Entities to Redact", "type": "text", "default": "PHONE_NUMBER, EMAIL_ADDRESS, PERSON, CREDIT_CARD", "description": "Comma-separated list of Presidio entities to detect."}, {"key": "score_threshold", "label": "PII Score Threshold", "type": "number", "default": 0.6, "description": "Confidence score threshold (0.0 to 1.0) for PII detection."}, {"key": "additional_profanity_words", "label": "Additional Profane Words", "type": "textarea", "default": "", "description": "Additional comma-separated profane words to redact."}, {"key": "additional_sensitive_keywords", "label": "Additional Sensitive Keywords", "type": "textarea", "default": "", "description": "Additional comma-separated sensitive keywords to redact."}, {"key": "filter_mode", "label": "Filter Mode", "type": "choice", "options": ["all", "include", "exclude"], "default": "all", "description": "Select whether to scan all fields, target specific fields, or exclude specific fields."}, {"key": "target_fields", "label": "Target Fields", "type": "text", "default": "", "description": "Comma-separated list of target fields to include or exclude (e.g., query, response)."}, {"key": "enable_pii", "label": "Enable PII Redaction", "type": "boolean", "default": true, "description": "Masks personally identifiable information (emails, names, phone numbers)."}]','[{"key": "profanity_words_system", "label": "System Baseline Profanities", "type": "textarea", "default": "fuck, shit, asshole, bitch, cunt, bastard", "description": "System-wide baseline profanities (comma-separated)."}, {"key": "sensitive_keywords_system", "label": "System Baseline Keywords", "type": "textarea", "default": "confidential, internal-only, secret", "description": "System-wide baseline sensitive keywords (comma-separated)."}]','{}','{}',NULL);
INSERT INTO nodes VALUES(27,'passthrough_trigger_node','Base Node','DEFAULT','Standard node base','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{}','{}',NULL);
INSERT INTO nodes VALUES(28,'dummy_test_node','Base Node','DEFAULT','Standard node base','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{}','{}',NULL);
INSERT INTO nodes VALUES(29,'contract_dummy_target_node','Base Node','DEFAULT','Standard node base','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{"type": "object", "properties": {"query_type": {"type": "string"}, "field_values": {"type": "array", "items": {"type": "array"}}}, "required": ["query_type", "field_values"]}','{}',NULL);
INSERT INTO nodes VALUES(30,'dummy_source_node','Base Node','DEFAULT','Standard node base','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{}','{}',NULL);
INSERT INTO nodes VALUES(31,'dummy_target_node','Base Node','DEFAULT','Standard node base','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{"query": {"type": "string", "required": true}, "limit": {"type": "integer", "required": true}}','{}',NULL);
INSERT INTO nodes VALUES(32,'client_6_test_custom_startup_node','Test Startup Node','DEFAULT','Mock node','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{}','{}',6);
INSERT INTO nodes VALUES(33,'client_10_test_custom_startup_node','Test Startup Node','DEFAULT','Mock node','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{}','{}',10);
INSERT INTO nodes VALUES(34,'client_1_sap_agent','Base Node','DEFAULT','Standard node base','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'{}','{}','{"version": "1.0", "rules": [], "additional_fields": true}','{}',1);
CREATE TABLE IF NOT EXISTS "workflow_nodes" (
    id INTEGER NOT NULL,
    workflow_id VARCHAR NOT NULL,
    agent_node_id VARCHAR,
    description varchar,
    agent_name varchar,
    updated_at VARCHAR,
    PRIMARY KEY (id),
    FOREIGN KEY (workflow_id) REFERENCES workflows (id)
);
INSERT INTO workflow_nodes VALUES(1,'external_api','api_webhook_agent_1782579449688',NULL,'api_webhook_agent','2026-06-27T19:23:56.231205');
INSERT INTO workflow_nodes VALUES(2,'external_api','external_api_node_1782579453575',NULL,'external_api_node','2026-06-27T19:23:56.231205');
INSERT INTO workflow_nodes VALUES(38,'sentiment_analyis','sentiment_analyzer_1782672296380',NULL,'sentiment_analyzer','2026-07-02T19:00:04.598341');
INSERT INTO workflow_nodes VALUES(39,'sentiment_analyis','scheduler_agent_1782935753755',NULL,'scheduler_agent','2026-07-02T19:00:04.598341');
INSERT INTO workflow_nodes VALUES(75,'mysql','generic_mysql_query_executor_1782762522453',NULL,'generic_mysql_query_executor','2026-07-07T11:05:57.811160');
INSERT INTO workflow_nodes VALUES(76,'mysql','api_webhook_agent_1782762814888',NULL,'api_webhook_agent','2026-07-07T11:05:57.811160');
INSERT INTO workflow_nodes VALUES(77,'mysql','profanity_guard_1782991097568',NULL,'profanity_guard','2026-07-07T11:05:57.811160');
INSERT INTO workflow_nodes VALUES(78,'eod_stocks','stocks_api_request_node_1782722681073',NULL,'stocks_api_request_node','2026-07-10T08:10:40.759207');
INSERT INTO workflow_nodes VALUES(79,'eod_stocks','stocks_webhook_agent_1782723972280',NULL,'stocks_webhook_agent','2026-07-10T08:10:40.759207');
INSERT INTO workflow_nodes VALUES(80,'eod_stocks','generic_mysql_query_executor_1782763274758',NULL,'generic_mysql_query_executor','2026-07-10T08:10:40.759207');
INSERT INTO workflow_nodes VALUES(81,'eod_stocks','generic_mysql_query_executor_1783670890311',NULL,'generic_mysql_query_executor','2026-07-10T08:10:40.759207');
INSERT INTO workflow_nodes VALUES(82,'test-props-workflow-1783759458','guard-node-1',NULL,'unified_content_guard','2026-07-11T08:44:18.153818');
CREATE TABLE IF NOT EXISTS "workflow_node_properties" (
    id INTEGER NOT NULL,
    workflow_id VARCHAR NOT NULL,
    agent_node_id VARCHAR NOT NULL,
    agent_name VARCHAR,
    properties JSON,
    label VARCHAR,
    output_contract JSON,
    input_contract JSON,
    PRIMARY KEY (id),
    FOREIGN KEY (agent_name) REFERENCES nodes (name)
);
INSERT INTO workflow_node_properties VALUES(1,'external_api','api_webhook_agent_1782579449688','api_webhook_agent','{"base_path":"mysql"}',NULL,NULL,NULL);
INSERT INTO workflow_node_properties VALUES(2,'external_api','external_api_node_1782579453575','external_api_node','{"url": "www.bing.com", "protocol": "https", "method": "GET", "auth_key": "", "path": "/search", "api_path": "", "params": "[{\"q\":\"{{message}}\"}]", "auth_type": "API_KEY", "host": "www.bing.com", "mapping_template": "{\n  \"data\": \"{{ input_data.result }}\"\n}"}',NULL,NULL,NULL);
INSERT INTO workflow_node_properties VALUES(39,'sentiment_analyis','sentiment_analyzer_1782672296380','sentiment_analyzer','{"sentiment": "1", "another": "a"}','Sentiment Analyzer 989',NULL,NULL);
INSERT INTO workflow_node_properties VALUES(40,'sentiment_analyis','scheduler_agent_1782935753755','scheduler_agent','{}','Scheduler',NULL,NULL);
INSERT INTO workflow_node_properties VALUES(80,'mysql','generic_mysql_query_executor_1782762522453','generic_mysql_query_executor','{"database": "test", "table": "stocks", "query_type": "select", "db_port": "3306", "user_name": "admin", "db_host": "127.0.0.1", "password": "password", "secured": "false"}','MySQL Node','{"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": "False", "stateable": true}, {"field_name": "lastrowid", "field_type": "integer", "required": "False", "stateable": true}], "additional_fields": "True"}','{"version": "1.0", "rules": [{"field_name": "query_type", "field_type": "string", "required": false}, {"field_name": "query", "field_type": "string", "required": false}, {"field_name": "table_name", "field_type": "string", "required": false}, {"field_name": "fields", "field_type": "object", "required": false}, {"field_name": "field_names", "field_type": "array", "required": false}, {"field_name": "field_values", "field_type": "array", "required": false}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": "True"}');
INSERT INTO workflow_node_properties VALUES(81,'mysql','api_webhook_agent_1782762814888','api_webhook_agent','{"base_path": "docs", "workers": ""}','Base Web hook','{"result": {"data": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}','{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}');
INSERT INTO workflow_node_properties VALUES(82,'mysql','profanity_guard_1782991097568','profanity_guard','{}','Profanity Guard','{}','{"version": "1.0", "rules": [{"field_name": "id", "field_type": "string", "required": true, "min_length": 1, "max_length": 20, "redact": true}], "additional_fields": true}');
INSERT INTO workflow_node_properties VALUES(83,'eod_stocks','stocks_api_request_node_1782722681073','stocks_api_request_node','{"auth_key": "", "url": "eodhd.com", "protocol": "https", "method": "GET", "params": "api_token=69747bd28b3bd8.99561497&fmt=json", "auth_type": "NONE", "path": "/api/eod/{{stock_token}}", "api_path": "", "mapping_template": "{\n  \"stock_token\": \"{{stock_token}}\",\n  \"fmt\": \"{{fmt}}\"\n}"}','EODHD Stocks','{"version": "1.0", "rules": [{"field_name": "root[].date", "field_type": "phone", "required": false}, {"field_name": "root[].open", "field_type": "number", "required": false}, {"field_name": "root[].high", "field_type": "number", "required": false}, {"field_name": "root[].low", "field_type": "number", "required": false}, {"field_name": "root[].close", "field_type": "number", "required": false}, {"field_name": "root[].adjusted_close", "field_type": "number", "required": false}, {"field_name": "root[].volume", "field_type": "integer", "required": false}]}','{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}, {"field_name": "fmt", "field_type": "string", "required": true}], "additional_fields": true}');
INSERT INTO workflow_node_properties VALUES(84,'eod_stocks','stocks_webhook_agent_1782723972280','stocks_webhook_agent','{"base_path": "stocks", "required_fields": ["stock_token", "market", "fmt"], "stateable_fields": ["stock_token", "market", "fmt"]}','Stocks Webhook Agent','{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": false}, {"field_name": "fmt", "field_type": "string", "required": false}, {"field_name": "market", "field_type": "string", "required": false}]}','{"version": "1.0", "rules": [], "additional_fields": true}');
INSERT INTO workflow_node_properties VALUES(85,'eod_stocks','generic_mysql_query_executor_1782763274758','generic_mysql_query_executor','{"database": "test", "table": "stocks", "query_type": "insert", "db_port": "3306", "user_name": "root", "db_host": "127.0.0.1", "password": "password", "secured": "false", "mapping_template": "{\n  \"field_names\": [\n    \"date\",\n    \"close\",\n    \"open\"\n  ],\n  \"field_values\": [\n    \"{{root[].date}}\",\n    \"{{root[].open}}\",\n    \"{{root[].close}}\"\n  ]\n}"}','MySQL Node','{"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": true, "stateable": false}, {"field_name": "lastrowid", "field_type": "integer", "required": true, "stateable": false}]}','{"version": "1.0", "rules": [{"field_name": "query_type", "field_type": "string", "required": false}, {"field_name": "query", "field_type": "string", "required": false}, {"field_name": "table_name", "field_type": "string", "required": false}, {"field_name": "fields", "field_type": "object", "required": false}, {"field_name": "field_names", "field_type": "array", "required": false}, {"field_name": "field_values", "field_type": "array", "required": false}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": "True"}');
INSERT INTO workflow_node_properties VALUES(86,'eod_stocks','generic_mysql_query_executor_1783670890311','generic_mysql_query_executor','{"database": "test", "table": "temp", "query_type": "insert,delete,update,select", "db_port": "3306", "user_name": "root", "db_host": "127.0.0.1", "password": "password", "secured": "false"}','MySQL Node','{"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": "False"}, {"field_name": "lastrowid", "field_type": "integer", "required": "False"}], "additional_fields": "True"}','{"version": "1.0", "rules": [{"field_name": "table_name", "field_type": "string", "required": true}, {"field_name": "fields", "field_type": "object", "required": true}, {"field_name": "field_names", "field_type": "array", "required": true}, {"field_name": "field_values", "field_type": "array", "required": true}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": true}');
INSERT INTO workflow_node_properties VALUES(87,'test-props-workflow-1783759458','guard-node-1','unified_content_guard','{"enable_pii": false, "mapping_template": "{\"msg\": \"{{input_data.text}}\"}"}','Renamed Acme Guard','null','null');
CREATE TABLE IF NOT EXISTS "audit_logs" (
	id INTEGER NOT NULL, 
	action VARCHAR NOT NULL, 
	resource_type VARCHAR NOT NULL, 
	resource_id VARCHAR, 
	status VARCHAR NOT NULL, 
	actor_user_id INTEGER, 
	actor_role VARCHAR, 
	customer_id INTEGER, 
	details JSON, 
	created_at VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(id) REFERENCES users (id)
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);
INSERT INTO audit_logs VALUES(9001,'test_action_1','workflow','wf-1','success',2002,'admin',10,NULL,'2026-07-10T12:00:00Z');
INSERT INTO audit_logs VALUES(9002,'test_action_2','workflow','wf-2','success',2001,'system_admin',20,NULL,'2026-07-10T13:00:00Z');
CREATE TABLE knowledge_chunks (
	id INTEGER NOT NULL, 
	document_id INTEGER NOT NULL, 
	knowledge_base_id INTEGER NOT NULL, 
	customer_id INTEGER NOT NULL, 
	chunk_index INTEGER NOT NULL, 
	content VARCHAR NOT NULL, 
	metadata_json JSON, 
	created_at VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES knowledge_documents (id), 
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);
INSERT INTO knowledge_chunks VALUES(1,1,1,1,0,unistr('Enterprise LLM Gateway allows businesses to create AI agents that automate workflows.\u000a\u000aThe platform supports workflow orchestration, knowledge retrieval, guardrails, observability, and human approval workflows.\u000a\u000aCustomer data is isolated by tenant.\u000a'),'null','2026-07-12T10:32:54.416009');
INSERT INTO knowledge_chunks VALUES(2,2,1,1,0,unistr('Enterprise LLM Gateway allows businesses to create AI agents that automate workflows.\u000a\u000aThe platform supports workflow orchestration, knowledge retrieval, guardrails, observability, and human approval workflows.\u000a\u000aCustomer data is isolated by tenant.\u000a'),'null','2026-07-12T14:27:15.996942');
INSERT INTO knowledge_chunks VALUES(3,3,1,1,0,unistr('Enterprise LLM Gateway allows businesses to create AI agents that automate workflows.\u000a\u000aThe platform supports workflow orchestration, knowledge retrieval, guardrails, observability, and human approval workflows.\u000a\u000aCustomer data is isolated by tenant.\u000a'),'null','2026-07-12T14:44:06.119481');
CREATE TABLE IF NOT EXISTS "knowledge_bases" (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	description VARCHAR, 
	status VARCHAR, 
	customer_id INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	settings JSON, 
	created_at VARCHAR, 
	updated_at VARCHAR, 
    file_path varchar, 
    file_size  integer,
    checksum varchar,
    chunk_count integer,
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
INSERT INTO knowledge_bases VALUES(1,'Product Documentation','Test knowledge base for Enterprise LLM Gateway','active',1,5,'null','2026-07-12T10:26:16.029624','2026-07-12T10:26:16.029654',NULL,NULL,NULL,NULL);
INSERT INTO knowledge_bases VALUES(2,'Product Documentation','Product knowledge base','active',1,5,'null','2026-07-12T14:34:21.520888','2026-07-12T14:34:21.520963',NULL,NULL,NULL,NULL);
INSERT INTO knowledge_bases VALUES(3,'Product Documentation','Product knowledge base','active',1,5,'null','2026-07-12T14:34:26.270353','2026-07-12T14:34:26.270376',NULL,NULL,NULL,NULL);
CREATE TABLE IF NOT EXISTS "knowledge_documents" (
	id INTEGER NOT NULL, 
	knowledge_base_id INTEGER NOT NULL, 
	customer_id INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	source_type VARCHAR, 
	source_uri VARCHAR, 
	mime_type VARCHAR, 
	metadata_json JSON, 
	status VARCHAR, 
	error_message VARCHAR, 
	created_at VARCHAR, 
	updated_at VARCHAR, 
	file_path varchar, 
    file_size  integer,
    checksum varchar,
    chunk_count integer,
	PRIMARY KEY (id), 
	FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
INSERT INTO knowledge_documents VALUES(1,1,1,5,'sample.txt','upload',NULL,'text/plain',NULL,'failed','OPENAI_API_KEY is not configured','2026-07-12T10:32:54.395716','2026-07-12T10:32:54.422651','data/knowledge/1/1/a457c99086bf49b5a23b4d2fb043c7fa.txt',249,'d941bb1cabeca29458190b3b9ecffe3550155d4f96c09fffa97e2097dc2ddde6',1);
INSERT INTO knowledge_documents VALUES(2,1,1,5,'sample.txt','upload',NULL,'text/plain',NULL,'ready',NULL,'2026-07-12T14:27:15.987661','2026-07-12T14:27:15.997737','data/knowledge/1/1/fdd621ec0b0c491faf80ea2ec9faf9db.txt',249,'d941bb1cabeca29458190b3b9ecffe3550155d4f96c09fffa97e2097dc2ddde6',1);
INSERT INTO knowledge_documents VALUES(3,1,1,5,'sample.txt','upload',NULL,'text/plain',NULL,'ready',NULL,'2026-07-12T14:44:06.109558','2026-07-12T14:44:06.120058','data/knowledge/1/1/d9618728407c49bfb00f0dde58f0c383.txt',249,'d941bb1cabeca29458190b3b9ecffe3550155d4f96c09fffa97e2097dc2ddde6',1);
CREATE INDEX ix_categories_id ON categories (id);
CREATE UNIQUE INDEX ix_categories_group ON categories ("group");
CREATE UNIQUE INDEX ix_credentials_name ON credentials (name);
CREATE INDEX ix_credentials_id ON credentials (id);
CREATE UNIQUE INDEX ix_oauth_providers_name ON oauth_providers (name);
CREATE INDEX ix_oauth_providers_id ON oauth_providers (id);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_workflows_id ON workflows (id);
CREATE INDEX ix_customers_id ON customers (id);
CREATE UNIQUE INDEX ix_customers_domain ON customers (domain);
CREATE UNIQUE INDEX ix_customers_name ON customers (name);
CREATE INDEX ix_customer_nodes_id ON customer_nodes (id);
CREATE INDEX ix_customer_nodes_customer_id ON customer_nodes (customer_id);
CREATE INDEX ix_customer_nodes_node_name ON customer_nodes (node_name);
CREATE INDEX ix_nodes_id ON nodes (id);
CREATE UNIQUE INDEX ix_nodes_name ON nodes (name);
CREATE INDEX ix_workflow_nodes_id ON workflow_nodes (id);
CREATE INDEX ix_workflow_node_properties_agent_node_id ON workflow_node_properties (agent_node_id);
CREATE INDEX ix_workflow_node_properties_id ON workflow_node_properties (id);
CREATE INDEX ix_workflow_node_properties_workflow_id ON workflow_node_properties (workflow_id);
CREATE INDEX ix_workflow_node_properties_agent_name ON workflow_node_properties (agent_name);
CREATE INDEX ix_audit_logs_resource_type ON audit_logs (resource_type);
CREATE INDEX ix_audit_logs_actor_role ON audit_logs (actor_role);
CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX ix_audit_logs_resource_id ON audit_logs (resource_id);
CREATE INDEX ix_audit_logs_id ON audit_logs (id);
CREATE INDEX ix_audit_logs_customer_id ON audit_logs (customer_id);
CREATE INDEX ix_audit_logs_status ON audit_logs (status);
CREATE INDEX ix_audit_logs_action ON audit_logs (action);
CREATE INDEX ix_audit_logs_actor_user_id ON audit_logs (actor_user_id);
CREATE INDEX ix_knowledge_chunks_knowledge_base_id ON knowledge_chunks (knowledge_base_id);
CREATE INDEX ix_knowledge_chunks_id ON knowledge_chunks (id);
CREATE INDEX ix_knowledge_chunks_customer_id ON knowledge_chunks (customer_id);
CREATE INDEX ix_knowledge_chunks_document_id ON knowledge_chunks (document_id);
CREATE INDEX ix_knowledge_bases_name ON knowledge_bases (name);
CREATE INDEX ix_knowledge_bases_created_by ON knowledge_bases (created_by);
CREATE INDEX ix_knowledge_bases_status ON knowledge_bases (status);
CREATE INDEX ix_knowledge_bases_id ON knowledge_bases (id);
CREATE INDEX ix_knowledge_bases_customer_id ON knowledge_bases (customer_id);
CREATE INDEX ix_knowledge_documents_customer_id ON knowledge_documents (customer_id);
CREATE INDEX ix_knowledge_documents_knowledge_base_id ON knowledge_documents (knowledge_base_id);
CREATE INDEX ix_knowledge_documents_created_by ON knowledge_documents (created_by);
CREATE INDEX ix_knowledge_documents_id ON knowledge_documents (id);
CREATE INDEX ix_knowledge_documents_status ON knowledge_documents (status);
COMMIT;
