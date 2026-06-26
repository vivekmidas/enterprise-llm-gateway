PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS  categories (
	id INTEGER NOT NULL, 
	"group" VARCHAR, 
	icon VARCHAR, 
	color VARCHAR, 
	label VARCHAR, 
	description VARCHAR, 
	PRIMARY KEY (id)
);
delete from categories;
INSERT INTO categories VALUES(1,'LLM Engines','Brain','#8b5cf6','Large Language Model','Core language model execution points and agent instances');
INSERT INTO categories VALUES(2,'Safety Guardrails','ShieldAlert','#ef4444','Guard Rails','Real-time validators for safety, compliance, and PII masking.');
INSERT INTO categories VALUES(3,'External Systems','box','#0A1dde','External Systems','Call external Systems');
INSERT INTO categories VALUES(4,'Communicaation','mail','#ff000a','Mails','Mails, SMS, WhatsAPP etc..');
INSERT INTO categories VALUES(5,'Data Operations','database','#06b6d4','Databases','DB queries, API calls, and inline scripts/variable setters.');
INSERT INTO categories VALUES(6,'Control Logic','gitfork','#f59e0b','Logic','Conditional routers, branching, and data transformations');
INSERT INTO categories VALUES(7,'Context & Memory','history','#3b82f6','Memory',unistr('Chat history managers and context injection helpers.\u0009Context Setter, Session Memory, RAG Embeddings\u000aAlerts\u0009Notifications\u0009Bell\u0009Orange (#f97316)\u0009Integration points for sending logs, emails, or chat alerts.\u0009Slack Notification, Send SMTP Mail, Audit Logger\u000a8. Alignment Implementation Steps\u000aDatabase Migration: Update backend/app/core/db.sql and run a schema migration to seed the categories table with the new IDs, colors, icons, and descriptions matching the grid above.\u000aFrontend Synchronization: Update frontend/app/components/component-categoriees.ts to map the CATEGORIES record to match the backend database labels and icons.\u000aPalette UI Revamp: Adjust the sidebar selector categories to display badges matching the Visual Theme colors for a clean cockpit feeling.\u000a'));
INSERT INTO categories VALUES(9,'Alerts','bell','#f97316','Integration','Integration points for sending logs, emails, or chat alerts.');
INSERT INTO categories VALUES(10,'Vector Databases','blocks','#10b981','Vector DB','Store and query high-dimensional vector embeddings.');
CREATE TABLE IF NOT EXISTS "workflow_nodes" (
	id INTEGER NOT NULL, 
	workflow_id VARCHAR NOT NULL, 
	agent_node_id VARCHAR, 
	description varchar,
	agent_name varchar,
	updated_at VARCHAR, 
	properties JSON, 
	PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS credentials (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	type VARCHAR NOT NULL, 
	config JSON NOT NULL, 
	auth_data JSON, 
	created_at VARCHAR, 
	updated_at VARCHAR, 
	PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS oauth_providers (
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
CREATE TABLE IF NOT EXISTS customers (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	domain VARCHAR, 
	status VARCHAR, 
	icon VARCHAR,
	color_schema VARCHAR,
	dateadded VARCHAR, 
	dateupdated VARCHAR, 
	PRIMARY KEY (id)
);
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
	PRIMARY KEY (id)
);
INSERT INTO users VALUES(1,'admin@gateway.com','admin@gateway.com','$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI','test test',NULL,'active','system_admin','2026-06-15T06:54:24.944840','2026-06-15T06:54:24.944863');
INSERT INTO users VALUES(2,'vivek@midasminds.in','vivek@midasminds.in','$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI','Vivek Jain',NULL,'active','user','2026-06-15T07:02:43.832758','2026-06-15T07:02:43.832776');
INSERT INTO users VALUES(3,'test@test.com','test@test.com','$argon2id$v=19$m=1024,t=2,p=8$Dwx8YxEUwfFTRjZ1G9PAwQ$BpcCREYOMFO5IDAAhDXhvwYBH81YniJdxDDuaZXXFg8','test test',NULL,'active','user','2026-06-15T11:54:01.515901','2026-06-15T11:54:01.516496');
INSERT INTO users VALUES(4,'test@example.com','test@example.com','$argon2id$v=19$m=1024,t=2,p=8$JaHhi49W9hp61Yn3sln5qg$VPC5u0pFyJ1yF8YsCFeah2vcuiqco1y4jPAoLEvsC4g','Test User',NULL,'active','user','2026-06-22T07:16:57.721383','2026-06-22T07:16:57.721407');
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
	customer_id varchar,
	user_id varchar,
	PRIMARY KEY (id)
);
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
	output_contract JSOM,
	PRIMARY KEY (id)
);
delete from nodes;
INSERT INTO nodes VALUES(0,'database_node','Database','NODE','Connects to most common database ','1.0.0','5',NULL,'database','#772711',NULL,NULL,NULL,'[]','[]',0,NULL);
INSERT INTO nodes VALUES(1,'context_setter','Context Setter','NODE','Enriches input with user context from CRM / DB','1.0.0','1',NULL,'User','#7C3000','Trigger','Call any LLM','[{"key": "test2411", "label": "test", "type": "string", "default": "1"}]','[]','[{"key": "key", "default": "test2411"}, {"key": "label", "default": "test"}, {"key": "type", "default": "string"}, {"key": "default", "default": "1"}]','{"version": "1.0", "rules": [{"field_name": "user_id", "field_type": "string", "required": true, "min_length": 1, "max_length": 48}], "additional_fields": true}','{"user_id": "", "data": []}');
INSERT INTO nodes VALUES(2,'custom_rule_guard','Custom Rule','NODE','Dynamic rule-based guard using JSON config','1.0.0','2',NULL,'bot','#C01010','Node',NULL,'[]','[]','{"test": "test"}',0,NULL);
INSERT INTO nodes VALUES(3,'generic_llm_agent','LLM Agent','NODE','Calls an LLM via specific IP and Port using OpenAI-compatible API','1.0.0','1',NULL,'Brain','#17a2b8','Node','Calls any LLM at the given port with the system prompt','[]','[]','[{"key": "ip", "default": "127.0.0.1"}, {"key": "port", "default": "11434"}, {"key": "temperature", "default": "0.5"}, {"key": "system_prompt", "default": "you are a helpful assistant"}, {"key": "model_name", "default": "qwen:0.5b"}]','{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}',NULL);
INSERT INTO nodes VALUES(4,'output_guard','Output Guard','NODE','Final safety check - PII leak, MAD, policy compliance','1.0.0','2',NULL,'bot','#7C3AED','Node',NULL,'[{"key": "checkPII", "type": "boolean", "label": "Check for PII leaks", "default": true}, {"key": "checkMAD", "type": "boolean", "label": "Check for MAD (Misogyny, Ableism, Discrimination)", "default": true}, {"key": "checkPolicy", "type": "boolean", "label": "Check for custom policy violations", "default": false}]','[]','[]',0,NULL);
INSERT INTO nodes VALUES(5,'presidio_ner_guard','NER Guard','NODE','Advanced PII + Custom Rules using Presidio','1.1.0','1',NULL,'bot','#ff6803','Node',NULL,'[]','[]','[]',0,NULL);
INSERT INTO nodes VALUES(6,'profanity_guard','Profanity Guard','NODE','Profanity and offensive content detection','1.1.0','2',NULL,'bot','#ffb700','Node',NULL,'[{"key": "enabled", "label": "Enabled", "type": "boolean"}, {"key": "sensitivity", "label": "Sensitivity", "type": "choice", "options": ["low", "medium", "high"]}]','[]','[]','{"version": "1.0", "rules": [{"field_name": "id", "field_type": "string", "required": true, "min_length": 1, "max_length": 20, "redact": true}], "additional_fields": true}',NULL);
INSERT INTO nodes VALUES(7,'scheduler_agent','Scheduler','TRIGGER','Trigger scheder after n seconds','1.0.0','2',NULL,'Clock','#0000CC','Node',NULL,'[]','[]','[]','{"version": "1.0", "rules": [{"field_name": "user_id", "field_type": "json", "required": true}], "additional_fields": true}',NULL);
INSERT INTO nodes VALUES(8,'sentiment_analyzer','Sentiment Analyzer','NODE','Analyzes sentiment of user message','1.0.0','3',NULL,'bot','#12239e','Node',NULL,'[{"key": "senstivity", "label": "senstivity", "type": "string", "default": ".5"}]','[{"key": "sentiment", "default": "1"}, {"key": "another", "default": "a"}]','[{"key": "sentiment", "default": "1"}]',0,NULL);
INSERT INTO nodes VALUES(9,'api_webhook_agent','Base Web hook','TRIGGER','API Webhook Agent for external system integration','1.0.0','2',NULL,'Cloud','#7C3AED','Node',NULL,'[]','[]','[{"key": "port", "default": "8888"}, {"key": "host", "default": "0.0.0.0"}, {"key": "workers", "default": "1"}]','{"version": "1.0", "rules": [], "additional_fields": true}','{"result": {"data": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}');
INSERT INTO nodes VALUES(10,'external_api_node','External API','NODE','Calls the third party API ','1.0.0','1','','Cloud','#5E0CEC','Node','','[{"key": "url", "label": "URL", "type": "string", "multiple": false, "default": "0.0.0.0"}, {"key": "path", "label": "path", "type": "string", "default": "/path"}, {"key": "api_path", "label": "api_path", "type": "string", "default": ""}, {"key": "port", "label": "port", "type": "string", "default": "80"}, {"key": "method", "label": "method", "type": "string", "default": "GET"}, {"key": "auth_token", "label": "Auth Token", "type": "string", "default": "-"}, {"key": "protocol", "label": "Protocol", "type": "string", "multiple": false, "default": "HTTP/ HTTPS"}, {"key": "auth_type", "label": "Auth Type", "type": "choice", "default": "[\"DB\",\"Auth_Token\"]"}]','[{"key": "url", "default": "www.bing.com/search"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "auth_key", "default": ""}, {"key": "path", "default": "/search"}, {"key": "api_path", "default": ""}, {"key": "params", "default": "[{\"q\":\"{{message}}\"}]"}, {"key": "auth_type", "default": "API_KEY"}]','[{"key": "host", "default": "www.bing.com"}, {"key": "auth_type", "default": "API_KEY"}]','{"version": "1.0", "rules": [], "additional_fields": true}',NULL);
INSERT INTO nodes VALUES(11,'gmail_email_trigger','Gmail','TRIGGER','Polls an IMAP server for new messages and triggers the workflow.','1.0.0','4',NULL,'mail','#EA4335',NULL,NULL,'[{"key": "auth", "label": "Auth Type", "type": "oauth"}]','[]','{"oauth": "oauth", "secret_key": "secret", "secret_value": "value", "client_id": "client", "email_id": "intuact@gmail.com"}',0,NULL);
INSERT INTO nodes VALUES(12,'sqlite_query_executor','SQLITE','TOOL','Connect to SQLITE Database and execute a query','1.0.0','5','','database','#0624BA','Node','','[{"key": "query_type", "label": "username", "type": "string", "default": ""}, {"key": "field_names", "label": "Field_names", "type": "string", "default": ""}, {"key": "field_values", "label": "Field Values", "type": "string", "default": ""}]','[]','{"path": "./database.db"}','{"data":{"field_names":{"values":[],"mandatory":"True"},"field_values":{"values":[],"mandatory":"True"},"query_type":{"type":"string","mandatory":"True"}}}','{"result": "{{message}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}');
INSERT INTO nodes VALUES(13,'transformer_node','Data Transformer','NODE','Transforms input data using Jinja2 templates to match the next node''s input','1.0.0','1',NULL,'shuffle','#c9980b',NULL,NULL,'[{"key": "test", "label": "test", "type": "string", "default": ""}, {"key": "name", "label": "name", "type": "string", "default": ""}]','[]','{"x": "x"}',NULL,NULL);
INSERT INTO nodes VALUES(14,'outlook_email_trigger','Outlook OAuth Trigger','TRIGGER','Polls Outlook via Microsoft Graph API for new messages.','1.0.0','1','Custom','mail','#EA4335','Node',NULL,NULL,'[]','{}','{}','{}');
INSERT INTO nodes VALUES(17,'stocks_webhook_agent','Stocks Webhook Agent','TRIGGER','Triggers workflows on stock price movements or API alerts','1.0.0','1','Custom','bot','#2ECC71','Node',NULL,NULL,'[]','[{"key": "port", "default": "8888"}, {"key": "host", "default": "0.0.0.0"}, {"key": "base_path", "default": "stocks"}]','{"version": "1.0", "rules": [], "additional_fields": true}','{}');
INSERT INTO nodes VALUES(18,'stocks_api_request_node','Stocks API Request NODE','NODE','Call STOCKS API to get latest stock quotes','1.0.0','1','Custom','bot','#5E0CEC','Node',NULL,NULL,'[]','[{"key": "auth_key", "default": ""}, {"key": "url", "default": "eodhd.com"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "params", "default": "api_token=69747bd28b3bd8.99561497&fmt=json"}, {"key": "auth_type", "default": "NONE"}, {"key": "path", "default": "/api/eod/{{stock_token}}"}, {"key": "api_path", "default": ""}]','{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}','{}');
INSERT INTO nodes VALUES(19,'generic_llm_vector_db','Base Node for strong data to VectorDB','NODE','Generic LLM node that stores embeddings in a VectorDB','1.0.0','10','Custom','blocks','#2cb23cff','Node',NULL,NULL,'[]','[{"key": "auth_key", "default": ""}, {"key": "url", "default": "eodhd.com"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "params", "default": "api_token=69747bd28b3bd8.99561497&fmt=json"}, {"key": "auth_type", "default": "NONE"}, {"key": "path", "default": "/api/eod/{{stock_token}}"}]','{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}','{}');

UPDATE nodes set node_type="NODE" where node_type ="DEFAULT";

CREATE TABLE IF NOT EXISTS "workflow_node_properties" (
	id INTEGER NOT NULL, 
	workflow_id VARCHAR NOT NULL, 
	agent_node_id VARCHAR NOT NULL, 
	agent_name VARCHAR, 
	properties JSON, 
	PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS "customer_nodes" (
	id INTEGER NOT NULL, 
	customer_id INTEGER NOT NULL, 
	node_name VARCHAR NOT NULL, 
	properties JSON, 
	is_enabled BOOLEAN DEFAULT 1, 
	updated_at VARCHAR, 
	PRIMARY KEY (id),
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);
CREATE INDEX ix_categories_id ON categories (id);
CREATE UNIQUE INDEX ix_categories_group ON categories ("group");
CREATE INDEX ix_workflow_nodes_id ON workflow_nodes (id);
CREATE UNIQUE INDEX ix_credentials_name ON credentials (name);
CREATE INDEX ix_credentials_id ON credentials (id);
CREATE UNIQUE INDEX ix_oauth_providers_name ON oauth_providers (name);
CREATE INDEX ix_oauth_providers_id ON oauth_providers (id);
CREATE INDEX ix_customers_id ON customers (id);
CREATE UNIQUE INDEX ix_customers_domain ON customers (domain);
CREATE UNIQUE INDEX ix_customers_name ON customers (name);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_workflows_id ON workflows (id);
CREATE INDEX ix_nodes_id ON nodes (id);
CREATE UNIQUE INDEX ix_nodes_name ON nodes (name);
CREATE INDEX ix_customer_nodes_id ON customer_nodes (id);
CREATE INDEX ix_customer_nodes_customer_id ON customer_nodes (customer_id);
CREATE INDEX ix_customer_nodes_node_name ON customer_nodes (node_name);
CREATE INDEX ix_workflow_node_properties_agent_node_id ON workflow_node_properties (agent_node_id);
CREATE INDEX ix_workflow_node_properties_id ON workflow_node_properties (id);
CREATE INDEX ix_workflow_node_properties_workflow_id ON workflow_node_properties (workflow_id);
CREATE INDEX ix_workflow_node_properties_agent_name ON workflow_node_properties (agent_name);
COMMIT;
