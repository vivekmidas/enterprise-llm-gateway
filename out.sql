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
INSERT INTO categories VALUES(1,'LLM','Brain','#805500','Large Language Model','Large Language Model');
INSERT INTO categories VALUES(2,'Guardrails','Fence','#990099','Guard Rails','Gaurd Rails');
INSERT INTO categories VALUES(3,'test','box','#0A1dde','Test','Test Categories');
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
INSERT INTO workflow_nodes VALUES(7,'webhookp_llm','api_webhook_agent_1781805857864',NULL,'api_webhook_agent','2026-06-19T09:51:42.409605',NULL);
INSERT INTO workflow_nodes VALUES(8,'webhookp_llm','generic_llm_agent_1781805863865',NULL,'generic_llm_agent','2026-06-19T09:51:42.409605',NULL);
INSERT INTO workflow_nodes VALUES(9,'webhookp_llm','sentiment_analyzer_1781862645761',NULL,'sentiment_analyzer','2026-06-19T09:51:42.409605',NULL);
INSERT INTO workflow_nodes VALUES(10,'new_agent','scheduler_agent_1781805690380',NULL,'scheduler_agent','2026-06-19T16:14:55.524712',NULL);
INSERT INTO workflow_nodes VALUES(11,'new_agent','context_setter_1781805700233',NULL,'context_setter','2026-06-19T16:14:55.524712',NULL);
INSERT INTO workflow_nodes VALUES(12,'test','scheduler_agent_1781887162039',NULL,'scheduler_agent','2026-06-19T16:39:38.133997',NULL);
INSERT INTO workflow_nodes VALUES(13,'test','generic_llm_agent_1781887165843',NULL,'generic_llm_agent','2026-06-19T16:39:38.133997',NULL);
CREATE TABLE workflow_node_properties (
	id INTEGER NOT NULL, 
	workflow_id VARCHAR NOT NULL, 
	agent_node_id VARCHAR NOT NULL, 
	agent_name VARCHAR, 
	"key" VARCHAR, 
	value VARCHAR, 
	PRIMARY KEY (id)
);
INSERT INTO workflow_node_properties VALUES(4,'webhookp_llm','api_webhook_agent_1781805857864','api_webhook_agent','user_properties','{"user_properties": {}, "input_contract": {"data": {"type": "json", "required": "True"}, "auth_token": {"type": "string", "required": "False"}, "source_system": {"type": "string", "required": "True"}, "event_type": {"type": "string", "required": "False"}, "request_id": {"type": "string", "required": "False"}}, "output_contract": {"result": {"data": {"message": "{{message}}"}, "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}}');
INSERT INTO workflow_node_properties VALUES(5,'webhookp_llm','api_webhook_agent_1781805857864','api_webhook_agent','input_contract','{"data": {"type": "json", "required": "True"}, "auth_token": {"type": "string", "required": "False"}, "source_system": {"type": "string", "required": "True"}, "event_type": {"type": "string", "required": "False"}, "request_id": {"type": "string", "required": "False"}}');
INSERT INTO workflow_node_properties VALUES(6,'webhookp_llm','api_webhook_agent_1781805857864','api_webhook_agent','output_contract','{"result": {"data": {"message": "{{message}}"}, "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}');
INSERT INTO workflow_node_properties VALUES(7,'webhookp_llm','sentiment_analyzer_1781862645761','sentiment_analyzer','sentiment','"1"');
INSERT INTO workflow_node_properties VALUES(8,'webhookp_llm','sentiment_analyzer_1781862645761','sentiment_analyzer','another','"a"');
INSERT INTO workflow_node_properties VALUES(9,'webhookp_llm','sentiment_analyzer_1781862645761','sentiment_analyzer','user_properties','{"sentiment": "1", "another": "a"}');
INSERT INTO workflow_node_properties VALUES(10,'webhookp_llm','sentiment_analyzer_1781862645761','sentiment_analyzer','input_contract','{}');
INSERT INTO workflow_node_properties VALUES(11,'webhookp_llm','sentiment_analyzer_1781862645761','sentiment_analyzer','output_contract','{}');
INSERT INTO workflow_node_properties VALUES(12,'new_agent','scheduler_agent_1781805690380','scheduler_agent','user_properties','{}');
INSERT INTO workflow_node_properties VALUES(13,'new_agent','scheduler_agent_1781805690380','scheduler_agent','input_contract','{}');
INSERT INTO workflow_node_properties VALUES(14,'new_agent','scheduler_agent_1781805690380','scheduler_agent','output_contract','{}');
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
INSERT INTO users VALUES(3,'test@test.com','test@test.com','$argon2id$v=19$m=1024,t=2,p=8$Dwx8YxEUwfFTRjZ1G9PAwQ$BpcCREYOMFO5IDAAhDXhvwYBH81YniJdxDDuaZXXFg8','test test',NULL,'active','user','2026-06-15T11:54:01.515901','2026-06-15T11:54:01.516496');
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
INSERT INTO workflows VALUES('new_agent','New Agent Test','',1,NULL,'default',NULL,'{"nodes": [{"id": "scheduler_agent_1781805690380", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "scheduler_agent", "label": "Scheduler", "description": "Trigger scheder after n seconds", "category": "2", "icon": "bot", "node_type": "TRIGGER", "id": 7, "version": "1.0.0", "group": null, "color": "#066524", "sub_label": null, "user_properties": [], "badge": "Node", "system_properties": {"scheduler_interval": "30", "unit": "[\"mins\",\"hours\",\"month\",\"days\"]"}, "executionStatus": "idle", "variant": "2", "subIcon": "bot", "model": "", "properties": {"user_properties": {}, "input_contract": {}, "output_contract": {}}}, "position": {"x": -139, "y": -14}, "measured": {"width": 150, "height": 52}, "selected": true, "dragging": false}, {"id": "context_setter_1781805700233", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "context_setter", "label": "Context Setter", "description": "Enriches input with user context from CRM / DB", "category": "1", "icon": "User", "node_type": "NODE", "id": 1, "version": "1.0.0", "group": null, "color": "#7C3000", "sub_label": "Call any LLM", "user_properties": [], "badge": "Trigger", "system_properties": {"key": "test2411", "label": "test", "type": "string", "default": "1"}, "executionStatus": "idle", "variant": "1", "subIcon": "User", "model": ""}, "position": {"x": 93, "y": -85}, "measured": {"width": 164, "height": 50}, "selected": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20, "color": "#94a3b8"}, "source": "scheduler_agent_1781805690380", "target": "context_setter_1781805700233", "id": "xy-edge__scheduler_agent_1781805690380-context_setter_1781805700233"}], "entry_point": "input_guard"}','2026-06-19T16:14:55.524712',1,NULL,'1');
INSERT INTO workflows VALUES('webhookp_llm','webhookp-llm','',1,NULL,'default',NULL,'{"nodes": [{"id": "api_webhook_agent_1781805857864", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "api_webhook_agent", "label": "Webhook", "description": "API Webhook Agent for external system integration", "category": "2", "icon": "Cloud", "node_type": "TRIGGER", "id": 9, "version": "1.0.0", "group": null, "color": "#be3aee", "sub_label": null, "user_properties": [], "badge": "Node", "system_properties": {"port": "8888", "workers": "1", "x": "x"}, "executionStatus": "idle", "variant": "2", "subIcon": "Cloud", "model": "", "properties": {"user_properties": {"user_properties": {}, "input_contract": {"data": {"type": "json", "required": "True"}, "auth_token": {"type": "string", "required": "False"}, "source_system": {"type": "string", "required": "True"}, "event_type": {"type": "string", "required": "False"}, "request_id": {"type": "string", "required": "False"}}, "output_contract": {"result": {"data": {"message": "{{message}}"}, "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}}, "input_contract": {"data": {"type": "json", "required": "True"}, "auth_token": {"type": "string", "required": "False"}, "source_system": {"type": "string", "required": "True"}, "event_type": {"type": "string", "required": "False"}, "request_id": {"type": "string", "required": "False"}}, "output_contract": {"result": {"data": {"message": "{{message}}"}, "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}}}, "position": {"x": -378.5, "y": -313.5}, "measured": {"width": 150, "height": 52}, "selected": false, "dragging": false}, {"id": "generic_llm_agent_1781805863865", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_llm_agent", "label": "LLM Agent", "description": "Calls an LLM via specific IP and Port using OpenAI-compatible API", "category": "1", "icon": "bot", "node_type": "NODE", "id": 3, "version": "1.0.0", "group": null, "color": "#5817ba", "sub_label": "Calls any LLM at the given port with the system prompt", "user_properties": [], "badge": "Node", "system_properties": {"ip": "127.0.0.1", "port": "11434", "temperature": "0.5", "system_prompt": "you are a helpful assistant", "model_name": "qwen:0.5b"}, "executionStatus": "idle", "variant": "1", "subIcon": "bot", "model": ""}, "position": {"x": 77.5, "y": -182.5}, "measured": {"width": 150, "height": 50}, "dragging": false, "selected": false}, {"id": "sentiment_analyzer_1781862645761", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "sentiment_analyzer", "label": "Sentiment Analyzer", "description": "Analyzes sentiment of user message", "category": "2", "icon": "bot", "node_type": "NODE", "id": 8, "version": "1.0.0", "group": null, "color": "#12239e", "sub_label": null, "system_properties": ["{\"key\":\"sentiment\",\"label\":\"sentiment\",\"type\":\"string\",\"value\":\"1\",\"default\":\"\"}"], "badge": "Node", "user_properties": ["{\"key\":\"sentiment\",\"label\":\"test\",\"type\":\"string\",\"value\":\"1\",\"default\":\"\"}", "{\"key\":\"another\",\"label\":\"another\",\"type\":\"string\",\"value\":\"a\",\"default\":\"\"}"], "properties": {"user_properties": {"sentiment": "1", "another": "a"}, "input_contract": {}, "output_contract": {}}, "executionStatus": "idle", "variant": "2", "subIcon": "bot", "model": ""}, "position": {"x": -76.5, "y": -448}, "measured": {"width": 200, "height": 50}, "selected": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20, "color": "#000000"}, "source": "sentiment_analyzer_1781862645761", "target": "generic_llm_agent_1781805863865", "id": "xy-edge__sentiment_analyzer_1781862645761-generic_llm_agent_1781805863865"}, {"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20, "color": "#000000"}, "source": "api_webhook_agent_1781805857864", "target": "sentiment_analyzer_1781862645761", "id": "xy-edge__api_webhook_agent_1781805857864-sentiment_analyzer_1781862645761"}], "entry_point": "input_guard"}','2026-06-19T09:51:42.409605',1,NULL,'1');
INSERT INTO workflows VALUES('test','test','test',1,NULL,'default',NULL,'{"nodes": [{"id": "scheduler_agent_1781887162039", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "scheduler_agent", "label": "Scheduler", "description": "Trigger scheder after n seconds", "category": "2", "icon": "Clock", "id": 7, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#24ff69", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": {"scheduler_interval": "30", "unit": "[\"mins\",\"hours\",\"month\",\"days\"]"}, "category_id": 2, "category_color": "#1DA1F2", "executionStatus": "idle", "variant": "2", "subIcon": "Clock", "model": ""}, "position": {"x": -66, "y": 93}, "measured": {"width": 150, "height": 50}, "dragging": false}, {"id": "generic_llm_agent_1781887165843", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_llm_agent", "label": "LLM Agent", "description": "Calls an LLM via specific IP and Port using OpenAI-compatible API", "category": "1", "icon": "Brain", "id": 3, "node_type": "NODE", "version": "1.0.0", "group": null, "color": "#17a2b8", "badge": "Node", "sub_label": "Calls any LLM at the given port with the system prompt", "user_properties": [], "system_properties": ["{\"key\":\"ip\",\"label\":\"ip\",\"type\":\"string\",\"value\":\"127.0.0.1\",\"default\":\"\"}", "{\"key\":\"port\",\"label\":\"port\",\"type\":\"string\",\"value\":\"11434\",\"default\":\"\"}", "{\"key\":\"temperature\",\"label\":\"temperature\",\"type\":\"string\",\"value\":\"0.5\",\"default\":\"\"}", "{\"key\":\"system_prompt\",\"label\":\"system_prompt\",\"type\":\"string\",\"value\":\"you are a helpful assistant\",\"default\":\"\"}", "{\"key\":\"model_name\",\"label\":\"model_name\",\"type\":\"string\",\"value\":\"qwen:0.5b\",\"default\":\"\"}"], "category_id": 1, "category_color": "#cc8800", "executionStatus": "idle", "variant": "1", "subIcon": "Brain", "model": ""}, "position": {"x": 242, "y": 79}, "measured": {"width": 150, "height": 50}}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20, "color": "#000000"}, "source": "scheduler_agent_1781887162039", "target": "generic_llm_agent_1781887165843", "id": "xy-edge__scheduler_agent_1781887162039-generic_llm_agent_1781887165843"}], "entry_point": "input_guard"}','2026-06-19T16:39:38.133997',1,NULL,'1');
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
INSERT INTO nodes VALUES(0,'database_node','Database','NODE','Connects to most common database ','1','5',NULL,'database','#772711',NULL,NULL,NULL,NULL,NULL,0,NULL);
INSERT INTO nodes VALUES(1,'context_setter','Context Setter','NODE','Enriches input with user context from CRM / DB','1.0.0','1',NULL,'User','#7C3000','Trigger','Call any LLM','[{"key": "test2411", "label": "test", "type": "string", "default": "1"}]','[]','{"key": "test2411", "label": "test", "type": "string", "default": "1"}','{"user_id": "", "datetime": "", "message": "{{message}}", "name": ""}','{"user_id": "", "data": []}');
INSERT INTO nodes VALUES(2,'custom_rule_guard','Custom Rule','NODE','Dynamic rule-based guard using JSON config','1.0.0','2',NULL,'bot','#C01010','Node',NULL,'[]','[]','{"test": "test"}',0,NULL);
INSERT INTO nodes VALUES(3,'generic_llm_agent','LLM Agent','NODE','Calls an LLM via specific IP and Port using OpenAI-compatible API','1.0.0','1',NULL,'Brain','#17a2b8','Node','Calls any LLM at the given port with the system prompt','[]','[]','["{\"key\":\"ip\",\"label\":\"ip\",\"type\":\"string\",\"value\":\"127.0.0.1\",\"default\":\"\"}", "{\"key\":\"port\",\"label\":\"port\",\"type\":\"string\",\"value\":\"11434\",\"default\":\"\"}", "{\"key\":\"temperature\",\"label\":\"temperature\",\"type\":\"string\",\"value\":\"0.5\",\"default\":\"\"}", "{\"key\":\"system_prompt\",\"label\":\"system_prompt\",\"type\":\"string\",\"value\":\"you are a helpful assistant\",\"default\":\"\"}", "{\"key\":\"model_name\",\"label\":\"model_name\",\"type\":\"string\",\"value\":\"qwen:0.5b\",\"default\":\"\"}"]',0,NULL);
INSERT INTO nodes VALUES(4,'output_guard','Output Guard','NODE','Final safety check - PII leak, MAD, policy compliance','1.0.0','2',NULL,'bot','#7C3AED','Node',NULL,'[{"key": "checkPII", "type": "boolean", "label": "Check for PII leaks", "default": true}, {"key": "checkMAD", "type": "boolean", "label": "Check for MAD (Misogyny, Ableism, Discrimination)", "default": true}, {"key": "checkPolicy", "type": "boolean", "label": "Check for custom policy violations", "default": false}]','[]','{"oauth": "oauth", "secret_key": "secret", "secret_value": "value", "client_id": "client", "email_id": "intuact@gmail.com"}',0,NULL);
INSERT INTO nodes VALUES(5,'presidio_ner_guard','Presidio NER Guard','NODE','Advanced PII + Custom Rules using Presidio','1.1.0','1',NULL,'bot','#ff6803','Node',NULL,'[]','[]','[]',0,NULL);
INSERT INTO nodes VALUES(6,'profanity_guard','Profanity Guard','NODE','Profanity and offensive content detection','1.1.0','2',NULL,'bot','#ffb700','Node',NULL,'[{"key": "enabled", "label": "Enabled", "type": "boolean"}, {"key": "sensitivity", "label": "Sensitivity", "type": "choice", "options": ["low", "medium", "high"]}]','[]','{}',0,NULL);
INSERT INTO nodes VALUES(7,'scheduler_agent','Scheduler','TRIGGER','Trigger scheder after n seconds','1.0.0','2',NULL,'Clock','#0000CC','Node',NULL,'[]','[]','{"scheduler_interval": "30", "unit": "[\"mins\",\"hours\",\"month\",\"days\"]"}',0,NULL);
INSERT INTO nodes VALUES(8,'sentiment_analyzer','Sentiment Analyzer','NODE','Analyzes sentiment of user message','1.0.0','3',NULL,'bot','#12239e','Node',NULL,'[{"key": "senstivity", "label": "senstivity", "type": "string", "default": ".5"}]','["{\"key\":\"sentiment\",\"label\":\"test\",\"type\":\"string\",\"value\":\"1\",\"default\":\"\"}", "{\"key\":\"another\",\"label\":\"another\",\"type\":\"string\",\"value\":\"a\",\"default\":\"\"}"]','["{\"key\":\"sentiment\",\"label\":\"sentiment\",\"type\":\"string\",\"value\":\"1\",\"default\":\"\"}"]',0,NULL);
INSERT INTO nodes VALUES(9,'api_webhook_agent','Webhook','TRIGGER','API Webhook Agent for external system integration','1.0.0','2',NULL,'Cloud','#7C3AED','Node',NULL,'[]','[]','{"port": "8888", "workers": "1", "x": "x"}','{"data":{"type":"json","required":"True"},"auth_token":{"type":"string","required":"False"},"source_system":{"type":"string","required":"True"},"event_type":{"type":"string","required":"False"},"request_id":{"type":"string","required":"False"}}','{"result":{"data":{"message":"{{message}}"},"error_code":"{{error_code}}","status":"{{status}}","error_message":"{{error_message}}"}}');
INSERT INTO nodes VALUES(10,'external_api_node','API','NODE','Calls the third party API ','1.0.0','1','','Cloud','#5E0CEC','Node','','[{"key": "url", "label": "URL", "type": "string", "multiple": false, "default": "0.0.0.0"}, {"key": "path", "label": "path", "type": "string", "default": "/path"}, {"key": "port", "label": "port", "type": "string", "default": "80"}, {"key": "method", "label": "method", "type": "string", "default": "GET"}, {"key": "auth_token", "label": "Auth Token", "type": "string", "default": "-"}, {"key": "protocol", "label": "Protocol", "type": "string", "multiple": false, "default": "HTTP/ HTTPS"}, {"key": "auth_type", "label": "Auth Type", "type": "choice", "default": "[\"DB\",\"Auth_Token\"]"}]','[]','{}',0,NULL);
INSERT INTO nodes VALUES(11,'gmail_email_trigger','Gmail','TRIGGER','Polls an IMAP server for new messages and triggers the workflow.','1.0.0','4',NULL,'mail','#EA4335',NULL,NULL,'[{"key": "auth", "label": "Auth Type", "type": "oauth"}]','[]','{"oauth": "oauth", "secret_key": "secret", "secret_value": "value", "client_id": "client", "email_id": "intuact@gmail.com"}',0,NULL);
INSERT INTO nodes VALUES(12,'sqlite_query_executor','SQLITE','NODE','Connect to SQLITE Database and execute a query','1.0.0','5','','database','#0624BA','Node','','[{"key": "query_type", "label": "username", "type": "string", "default": ""}, {"key": "field_names", "label": "Field_names", "type": "string", "default": ""}, {"key": "field_values", "label": "Field Values", "type": "string", "default": ""}]','[]','{"path": "./database.db"}','{"data":{"field_names":{"values":[],"mandatory":"True"},"field_values":{"values":[],"mandatory":"True"},"query_type":{"type":"string","mandatory":"True"}}}','{"result": "{{message}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}');
INSERT INTO nodes VALUES(13,'transformer_node','Data Transformer','TRANFORM','Transforms input data using Jinja2 templates to match the next node''s input','1.0','1',NULL,'shuffle','#c9980b',NULL,NULL,'[{"key": "test", "label": "test", "type": "string", "default": ""}, {"key": "name", "label": "name", "type": "string", "default": ""}]','[]','{"x": "x"}',NULL,NULL);
CREATE INDEX ix_categories_id ON categories (id);
CREATE UNIQUE INDEX ix_categories_group ON categories ("group");
CREATE INDEX ix_workflow_nodes_id ON workflow_nodes (id);
CREATE INDEX ix_workflow_node_properties_key ON workflow_node_properties ("key");
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
CREATE INDEX ix_workflows_id ON workflows (id);
CREATE INDEX ix_nodes_id ON nodes (id);
CREATE UNIQUE INDEX ix_nodes_name ON nodes (name);
COMMIT;
