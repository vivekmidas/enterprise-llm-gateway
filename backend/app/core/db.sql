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
INSERT INTO categories VALUES(1,'LLM','Brain','#fff000','Large Language Model','Large Language Model');
INSERT INTO categories VALUES(2,'Guardrails','Fence','#1DA1F2','Guard Rails','Gaurd Rails');
INSERT INTO categories VALUES(4,'Communicaation','mail','#ff000a','Mails','Mails, SMS, WhatsAPP etc..');
INSERT INTO categories VALUES(5,'Core','database','#1DA100','Databases','Connect to the database');
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
CREATE TABLE workflow_node_properties (
	id INTEGER NOT NULL, 
	workflow_id VARCHAR NOT NULL, 
	agent_node_id VARCHAR NOT NULL, 
	agent_name VARCHAR, 
	properties JSON, 
	PRIMARY KEY (id)
);
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
CREATE TABLE companies (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	domain VARCHAR, 
	status VARCHAR, 
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
	company_id VARCHAR, 
	status VARCHAR, 
	role VARCHAR, 
	created_at VARCHAR, 
	updated_at VARCHAR, 
	PRIMARY KEY (id)
);
INSERT INTO users VALUES(1,'admin@gateway.com','admin@gateway.com','$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI','test test',NULL,'active','admin','2026-06-15T06:54:24.944840','2026-06-15T06:54:24.944863');
INSERT INTO users VALUES(2,'vivek@midasminds.in','vivek@midasminds.in','$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI','Vivek Jain',NULL,'active','user','2026-06-15T07:02:43.832758','2026-06-15T07:02:43.832776');
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
	output_contract JSON,
	PRIMARY KEY (id)
);
INSERT INTO nodes VALUES(0,'database_node','Database','NODE','Connects to most common database ','1','5',NULL,'database','#772711',NULL,NULL,NULL,NULL,0,NULL);
INSERT INTO nodes VALUES(1,'context_setter','Context Setter','NODE','Enriches input with user context from CRM / DB','1.0.0','1',NULL,'User','#7C3000','Trigger','Call any LLM','[{"key": "test2411", "label": "test", "type": "string", "default": "1"}]','{"test2411": "122"}','{"user_id": "", "datetime": "", "data": "{{data}}", "name": ""}','{"data": {"type": "object", "properties": {"user_id": {"type": "string"}, "data": {"type": "array"}}}}',NULL);
INSERT INTO nodes VALUES(2,'custom_rule_guard','Custom Rule','NODE','Dynamic rule-based guard using JSON config','1.0.0','2',NULL,'bot','#C01010','Node',NULL,'[{"key": "test", "label": "test", "type": "string", "default": "test"}]','{"test": "test"}',0,NULL,NULL);
INSERT INTO nodes VALUES(3,'generic_llm_agent','LLM Agent','NODE','Calls an LLM via specific IP and Port using OpenAI-compatible API','1.0.0','1',NULL,'bot','#17a2b8','Node','Calls any LLM at the given port with the system prompt','[{"key": "ip", "label": "IP Address", "type": "string", "placeholder": "127.0.0.1"}, {"key": "port", "label": "Port", "type": "string", "placeholder": "8000"}, {"key": "model", "label": "Model Name", "type": "string", "placeholder": "default-model"}, {"key": "temperature", "label": "Temperature", "type": "number", "placeholder": "0.7"}, {"key": "systemPrompt", "label": "System Prompt", "type": "textarea"}]','{"ip": "127.0.0.1", "port": "11434", "model": "qwen:0.5b", "temperature": 0.7, "systemPrompt": "analyze the mail content sent and speicify the following \n1- priority - 1-5\n2- possible spam - 1-10\n3- context of the mail - max 50 words\n4- should respond ? yes/no\nreply in json with following fields \n{\"priority\":\"\",\"context\":\"\", \"spam_meter\":\"\", \"respond\":\"\"}"}',0,NULL,NULL);
INSERT INTO nodes VALUES(4,'output_guard','Output Guard','NODE','Final safety check - PII leak, MAD, policy compliance','1.0.0','2',NULL,'bot','#7C3AED','Node',NULL,'[{"key": "checkPII", "type": "boolean", "label": "Check for PII leaks", "default": true}, {"key": "checkMAD", "type": "boolean", "label": "Check for MAD (Misogyny, Ableism, Discrimination)", "default": true}, {"key": "checkPolicy", "type": "boolean", "label": "Check for custom policy violations", "default": false}]','{"checkPII": true, "checkMAD": true, "checkPolicy": false}',0,NULL,NULL);
INSERT INTO nodes VALUES(5,'presidio_ner_guard','Presidio NER Guard','NODE','Advanced PII + Custom Rules using Presidio','1.1.0','2',NULL,'bot','#ff6803','Node',NULL,'[]','{"property_1780474559938": "1", "property_1780474561488": "2"}',0,NULL,NULL);
INSERT INTO nodes VALUES(6,'profanity_guard','Profanity Guard','NODE','Profanity and offensive content detection','1.1.0','2',NULL,'bot','#ffb700','Node',NULL,'[{"key": "enabled", "label": "Enabled", "type": "boolean"}, {"key": "sensitivity", "label": "Sensitivity", "type": "choice", "options": ["low", "medium", "high"]}]','{"enabled": true, "sensitivity": "high"}',0,NULL,NULL);
INSERT INTO nodes VALUES(7,'scheduler_agent','Scheduler','TRIGGER','Runs a command or triggers an agent recurringly in the background','1.0.0','2',NULL,'bot','#24ff69','Node',NULL,'[{"key": "interval", "label": "Interval", "type": "number"}, {"key": "unit", "label": "Unit", "type": "choice", "options": ["seconds", "minutes"]}, {"key": "command", "label": "Shell Command", "type": "string"}, {"key": "targetAgent", "label": "Target Agent", "type": "choice", "options": []}]','{"interval": 100000, "unit": "minutes", "command": "", "targetAgent": ""}',0,NULL,NULL);
INSERT INTO nodes VALUES(8,'sentiment_analyzer','Sentiment Analyzer','NODE','Analyzes sentiment of user message','1.0.0','3',NULL,'bot','#12239e','Node',NULL,'[{"key": "senstivity", "label": "senstivity", "type": "string", "default": ".5"}]','{"property_1780670439840": "", "senstivity": ".5"}',0,NULL,NULL);
INSERT INTO nodes VALUES(9,'api_webhook_agent','Webhook','TRIGGER','API Webhook Agent for external system integration','1.0.0','2',NULL,'Cloud','#7C3AED','Node',NULL,'[]','{}','{"port": "8888", "host": "0.0.0.0", "workers": 1}','{"data":{"type":"json","required":"True"},"auth_token":{"type":"string","required":"False"},"source_system":{"type":"string","required":"True"},"event_type":{"type":"string","required":"False"},"request_id":{"type":"string","required":"False"}}','{"result":{"data":"{{data}}","error_code":"{{error_code}}","status":"{{status}}","error_message":"{{error_message}}"}}');
INSERT INTO nodes VALUES(10,'external_api_node','API','NODE','Calls the third party API ','1.0.0','1','','bot','#5E0CEC','Node','','[{"key": "url", "label": "URL", "type": "string", "multiple": false, "default": "0.0.0.0"}, {"key": "path", "label": "path", "type": "string", "default": "/path"}, {"key": "port", "label": "port", "type": "string", "default": "80"}, {"key": "method", "label": "method", "type": "string", "default": "GET"}, {"key": "auth_token", "label": "Auth Token", "type": "string", "default": "-"}, {"key": "protocol", "label": "Protocol", "type": "string", "multiple": false, "default": "HTTP/ HTTPS"}, {"key": "auth_type", "label": "Auth Type", "type": "choice", "default": "[\"DB\",\"Auth_Token\"]"}]','{"url": "https://www.msrit.edu/", "path": "/", "port": "80", "method": "GET", "auth_token": "", "protocol": "http", "auth_type": "DB"}',0,NULL,NULL);
INSERT INTO nodes VALUES(11,'gmail_email_trigger','Gmail','TRIGGER','Polls an IMAP server for new messages and triggers the workflow.','1.0.0','4',NULL,'mail','#EA4335',NULL,NULL,'[{"key": "auth", "label": "Auth Type", "type": "oauth"}]','{"auth": "0", "auth_client_id": "766633200484-v42quiqo5o3evg81ulrcud4np356o7be.apps.googleusercontent.com", "auth_client_secret": "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", "access_token": "ya29.a0AT3oNZ9Jkziw0VhH3nZF_y51qA6sNeZW4qfwYWUkgE1GBhK2PQ1XSW2H20oVh6SuzuAGvilAFhTgZr2Ek2cvNf8sztAcKGyt-eHCQALIEKipMQ7XecOCXWYPO-_9RZ8hWVJpI17DXDVFDPfcM0F690o7g4YmH9gWqmgakBhSqLplQ_JJDw9bFvyl9UN2OUK62nUCZe4aCgYKAagSARYSFQHGX2MiNQabeLEgkcfWpKG3LEjnYg0206", "refresh_token": "1//0g59nmZNs1DlYCgYIARAAGBASNwF-L9IrT7-U-dpkyRgKWzL3tO1kSZM5fbc61MSTQ-UH7KF2qLL-ts9BPmARfCrt6v962KNrJV8"}',0,NULL,NULL);
INSERT INTO nodes VALUES(12,'sqlite_query_executor','SQLITE','NODE','Connect to SQLITE Database and execute a query','1.0.0','5','','database','#0624BA','Node','','[{"key": "path", "label": "Path", "type": "string"}, {"key": "username", "label": "username", "type": "string"}, {"key": "password", "label": "password", "type": "string"}]','{"username": "", "password": "", "path": ""}','{}','{"data":{"field_names":{"values":[],"mandatory":"True"},"field_values":{"values":[],"mandatory":"True"},"query_type":{"type":"string","mandatory":"True"}}}','{"result": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}');
INSERT INTO nodes VALUES(13,'transformer_node','Data Transformer','TRANFORM','Transforms input data using Jinja2 templates to match the next node''s input','1.0','1',NULL,'shuffle','#c9980b',NULL,NULL,NULL,NULL,NULL,NULL);
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
	company_id varchar,
	user_id varchar,
	PRIMARY KEY (id)
);
CREATE INDEX ix_categories_id ON categories (id);
CREATE UNIQUE INDEX ix_categories_group ON categories ("group");
CREATE INDEX ix_workflow_nodes_id ON workflow_nodes (id);
CREATE INDEX ix_workflow_node_properties_agent_node_id ON workflow_node_properties (agent_node_id);
CREATE INDEX ix_workflow_node_properties_id ON workflow_node_properties (id);
CREATE INDEX ix_workflow_node_properties_workflow_id ON workflow_node_properties (workflow_id);
CREATE INDEX ix_workflow_node_properties_agent_name ON workflow_node_properties (agent_name);
CREATE UNIQUE INDEX ix_credentials_name ON credentials (name);
CREATE INDEX ix_credentials_id ON credentials (id);
CREATE UNIQUE INDEX ix_oauth_providers_name ON oauth_providers (name);
CREATE INDEX ix_oauth_providers_id ON oauth_providers (id);
CREATE INDEX ix_companies_id ON companies (id);
CREATE UNIQUE INDEX ix_companies_domain ON companies (domain);
CREATE UNIQUE INDEX ix_companies_name ON companies (name);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_nodes_id ON nodes (id);
CREATE UNIQUE INDEX ix_nodes_name ON nodes (name);
CREATE INDEX ix_workflows_id ON workflows (id);
COMMIT;
