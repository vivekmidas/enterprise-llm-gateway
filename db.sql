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
INSERT INTO categories VALUES(3,'test','box','#0A1dde','Test','Test Categories');
INSERT INTO categories VALUES(4,'Communicaation','mail','#ff000a','Mails','Mails, SMS, WhatsAPP etc..');
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
	properties JSON, 
	PRIMARY KEY (id)
);
INSERT INTO nodes VALUES(0,'database_node','Connects to a Database ','NODE','Connects to most common database ','1','1',NULL,'database','#772711',NULL,NULL,NULL,NULL);
INSERT INTO nodes VALUES(1,'context_setter','Context Setter','NODE','Enriches input with user context from CRM / DB','1.0.0','1',NULL,'User','#7C3000','Trigger','Call any LLM','[{"key": "test2411", "label": "test", "type": "string", "default": "1"}, {"key": "new property", "label": "New Property", "type": "string", "default": "3333"}]','{"new property": "222", "test2411": "122"}');
INSERT INTO nodes VALUES(2,'custom_rule_guard','custom_rule_guard','NODE','Dynamic rule-based guard using JSON config','1.0.0','3',NULL,'bot','#C01010','Node',NULL,'[{"key": "test", "label": "test", "type": "string", "default": "test"}]','{"test": "test"}');
INSERT INTO nodes VALUES(3,'generic_llm_agent','Generic LLM Agent','NODE','Calls an LLM via specific IP and Port using OpenAI-compatible API','1.0.0','2',NULL,'bot','#17a2b8','Node',NULL,'[{"key": "ip", "label": "IP Address", "type": "string", "placeholder": "127.0.0.1"}, {"key": "port", "label": "Port", "type": "string", "placeholder": "8000"}, {"key": "model", "label": "Model Name", "type": "string", "placeholder": "default-model"}, {"key": "temperature", "label": "Temperature", "type": "number", "placeholder": "0.7"}, {"key": "systemPrompt", "label": "System Prompt", "type": "textarea"}]','{"ip": "127.0.0.1", "port": "11434", "model": "qwen:0.5b", "temperature": 0.7, "systemPrompt": "analyze the mail content sent and speicify the following \n1- priority - 1-5\n2- possible spam - 1-10\n3- context of the mail - max 50 words\n4- should respond ? yes/no\nreply in json with following fields \n{\"priority\":\"\",\"context\":\"\", \"spam_meter\":\"\", \"respond\":\"\"}"}');
INSERT INTO nodes VALUES(4,'output_guard','Output Guard','NODE','Final safety check - PII leak, MAD, policy compliance','1.0.0','1',NULL,'bot','#7C3AED','Node',NULL,'[{"key": "checkPII", "type": "boolean", "label": "Check for PII leaks", "default": true}, {"key": "checkMAD", "type": "boolean", "label": "Check for MAD (Misogyny, Ableism, Discrimination)", "default": true}, {"key": "checkPolicy", "type": "boolean", "label": "Check for custom policy violations", "default": false}]','{"checkPII": true, "checkMAD": true, "checkPolicy": false}');
INSERT INTO nodes VALUES(5,'presidio_ner_guard','Presidio NER Guard','NODE','Advanced PII + Custom Rules using Presidio','1.1.0','1',NULL,'bot','#ff6803','Node',NULL,'[]','{"property_1780474559938": "1", "property_1780474561488": "2"}');
INSERT INTO nodes VALUES(6,'profanity_guard','Profanity Guard','NODE','Profanity and offensive content detection','1.1.0','2',NULL,'bot','#ffb700','Node',NULL,'[{"key": "enabled", "label": "Enabled", "type": "boolean"}, {"key": "sensitivity", "label": "Sensitivity", "type": "choice", "options": ["low", "medium", "high"]}]','{"enabled": true, "sensitivity": "high"}');
INSERT INTO nodes VALUES(7,'scheduler_agent','Scheduler Agent','TRIGGER','Runs a command or triggers an agent recurringly in the background','1.0.0','2',NULL,'bot','#24ff69','Node',NULL,'[{"key": "interval", "label": "Interval", "type": "number"}, {"key": "unit", "label": "Unit", "type": "choice", "options": ["seconds", "minutes"]}, {"key": "command", "label": "Shell Command", "type": "string"}, {"key": "targetAgent", "label": "Target Agent", "type": "choice", "options": []}]','{"interval": 100000, "unit": "minutes", "command": "", "targetAgent": ""}');
INSERT INTO nodes VALUES(8,'sentiment_analyzer','Sentiment Analyzer','NODE','Analyzes sentiment of user message','1.0.0','3',NULL,'bot','#12239e','Node',NULL,'[{"key": "senstivity", "label": "senstivity", "type": "string", "default": ".5"}]','{"property_1780670439840": "", "senstivity": ".5"}');
INSERT INTO nodes VALUES(9,'api_webhook_agent','Webhook','TRIGGER','API Webhook Agent for external system integration','1.0.0','2',NULL,'Cloud','#7C3AED','Node',NULL,'[{"key": "workers", "label": "Workers", "type": "string", "default": "1"}, {"key": "port", "label": "Port", "type": "string"}]','{"property_1780670099641": "9000", "property_1780670118773": "2", "workers": "1", "port": "9999"}');
INSERT INTO nodes VALUES(10,'external_api_node','External API Caller','NODE','Calls the third party API ','1.0.0','1','','bot','#5E0CEC','Node','','[{"key": "url", "label": "URL", "type": "string", "multiple": false, "default": "0.0.0.0"}, {"key": "path", "label": "path", "type": "string", "default": "/path"}, {"key": "port", "label": "port", "type": "string", "default": "80"}, {"key": "method", "label": "method", "type": "string", "default": "GET"}, {"key": "auth_token", "label": "Auth Token", "type": "string", "default": "-"}, {"key": "protocol", "label": "Protocol", "type": "string", "multiple": false, "default": "HTTP/ HTTPS"}]','{"url": "https://www.msrit.edu/", "path": "/", "port": "80", "method": "GET", "auth_token": "", "protocol": "http"}');
INSERT INTO nodes VALUES(11,'gmail_email_trigger','Gmail Email Trigger','TRIGGER','Polls an IMAP server for new messages and triggers the workflow.','1.0.0','4',NULL,'mail','#EA4335',NULL,NULL,'[{"key": "auth", "label": "Auth Type", "type": "oauth"}]','{"auth": "0", "auth_client_id": "766633200484-v42quiqo5o3evg81ulrcud4np356o7be.apps.googleusercontent.com", "auth_client_secret": "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"}');
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
INSERT INTO workflow_nodes VALUES(4,'scheuler','generic_llm_agent_1780916465461',NULL,'generic_llm_agent','2026-06-08T18:10:45.576054',NULL);
INSERT INTO workflow_nodes VALUES(5,'scheuler','scheduler_agent_1780940575916',NULL,'scheduler_agent','2026-06-08T18:10:45.576054',NULL);
INSERT INTO workflow_nodes VALUES(6,'external_api','external_api_node_1781013870631',NULL,'external_api_node','2026-06-09T19:14:28.886557',NULL);
INSERT INTO workflow_nodes VALUES(7,'external_api','api_webhook_agent_1781013883754',NULL,'api_webhook_agent','2026-06-09T19:14:28.886557',NULL);
INSERT INTO workflow_nodes VALUES(12,'test','api_webhook_agent_1781112710869',NULL,'api_webhook_agent','2026-06-11T17:29:39.969814',NULL);
INSERT INTO workflow_nodes VALUES(13,'test','profanity_guard_1781112713321',NULL,'profanity_guard','2026-06-11T17:29:39.969814',NULL);
INSERT INTO workflow_nodes VALUES(14,'scheduler','scheduler_agent_1781203597709',NULL,'scheduler_agent','2026-06-11T20:09:54.460650',NULL);
INSERT INTO workflow_nodes VALUES(15,'scheduler','database_node_1781208580497',NULL,'database_node','2026-06-11T20:09:54.460650',NULL);
INSERT INTO workflow_nodes VALUES(18,'email_processor','generic_llm_agent_1781251899714',NULL,'generic_llm_agent','2026-06-12T17:07:49.342662',NULL);
INSERT INTO workflow_nodes VALUES(19,'email_processor','gmail_email_trigger_1781267219334',NULL,'gmail_email_trigger','2026-06-12T17:07:49.342662',NULL);
INSERT INTO workflow_nodes VALUES(20,'email','generic_llm_agent_1781210129433',NULL,'generic_llm_agent','2026-06-12T17:08:38.875707',NULL);
INSERT INTO workflow_nodes VALUES(21,'email','api_webhook_agent_1781284096335',NULL,'api_webhook_agent','2026-06-12T17:08:38.875707',NULL);
INSERT INTO workflow_nodes VALUES(22,'new','gmail_email_trigger_1781354990348',NULL,'gmail_email_trigger','2026-06-13T12:55:02.637235',NULL);
INSERT INTO workflow_nodes VALUES(23,'new','context_setter_1781355217334',NULL,'context_setter','2026-06-13T12:55:02.637235',NULL);
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
	PRIMARY KEY (id)
);
INSERT INTO workflows VALUES('test','test','',1,NULL,'default',NULL,'{"id": "test", "version": "1", "name": "test", "description": "", "category": "default", "nodes_structure": [{"id": "api_webhook_agent_1781112710869", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "api_webhook_agent", "label": "Webhook", "description": "API Webhook Agent for external system integration", "category": "2", "icon": "Cloud", "node_type": "TRIGGER", "badge": "Node", "id": 9, "version": "1.0.0", "group": null, "color": "#7C3AED", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 155.96976744186048, "y": -99.24854651162794}, "width": 142, "height": 62, "selected": true, "dragging": false, "positionAbsolute": {"x": 155.96976744186048, "y": -99.24854651162794}}, {"id": "profanity_guard_1781112713321", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "profanity_guard", "label": "profanity_guard", "description": "Profanity and offensive content detection", "category": "2", "icon": "bot", "node_type": "NODE", "badge": "Node", "id": 6, "version": "1.1.0", "group": null, "color": "#ffb700", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 363.89331395348825, "y": -146.021511627907}, "width": 171, "height": 62, "selected": false, "dragging": false, "positionAbsolute": {"x": 363.89331395348825, "y": -146.021511627907}}], "edges": [{"type": "smoothstep", "animated": false, "markerEnd": {"type": "arrowclosed", "color": "#981a04ff", "height": 20, "width": 20}, "source": "api_webhook_agent_1781112710869", "sourceHandle": null, "target": "profanity_guard_1781112713321", "targetHandle": null, "id": "reactflow__edge-api_webhook_agent_1781112710869-profanity_guard_1781112713321", "selected": false}], "entry_point": "input_guard", "is_enabled": true, "updated_at": "2026-06-11T17:29:39.965785"}','2026-06-11T17:29:39.969814',1);
INSERT INTO workflows VALUES('scheduler','Scheduler','',1,NULL,'default',NULL,'{"id": "scheduler", "version": "1", "name": "Scheduler", "description": "", "category": "default", "nodes_structure": [{"id": "scheduler_agent_1781203597709", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "scheduler_agent", "label": "Scheduler Agent", "description": "Runs a command or triggers an agent recurringly in the background", "category": "2", "icon": "bot", "badge": "Node", "node_type": "TRIGGER", "id": 7, "version": "1.0.0", "group": null, "color": "#24ff69", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 114.41242732558129, "y": -270.45327034883724}, "width": 172, "height": 62, "selected": false}, {"id": "database_node_1781208580497", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "database_node", "label": "Connects to a Database ", "description": "Connects to most common database ", "category": "1", "icon": "database", "badge": null, "id": 0, "node_type": "NODE", "version": "1", "group": null, "color": "#772711", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 218.16242732558135, "y": -136.70327034883724}, "width": 208, "height": 62, "selected": true, "dragging": false, "positionAbsolute": {"x": 218.16242732558135, "y": -136.70327034883724}}], "edges": [{"type": "smoothstep", "animated": false, "markerEnd": {"type": "arrowclosed", "color": "#981a04ff", "height": 20, "width": 20}, "source": "scheduler_agent_1781203597709", "sourceHandle": null, "target": "database_node_1781208580497", "targetHandle": null, "id": "reactflow__edge-scheduler_agent_1781203597709-database_node_1781208580497", "selected": false}], "entry_point": "input_guard", "is_enabled": true, "updated_at": "2026-06-11T20:09:54.451961"}','2026-06-11T20:09:54.460650',1);
INSERT INTO workflows VALUES('email','Email','',1,NULL,'default',NULL,'{"id": "email", "version": "1", "name": "Email", "description": "", "category": "default", "nodes_structure": [{"id": "generic_llm_agent_1781210129433", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_llm_agent", "label": "Generic LLM Agent", "description": "Calls an LLM via specific IP and Port using OpenAI-compatible API", "category": "2", "icon": "bot", "badge": "Node", "id": 3, "node_type": "NODE", "version": "1.0.0", "group": null, "color": "#17a2b8", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 487, "y": 185}, "width": 189, "height": 62, "selected": false, "positionAbsolute": {"x": 487, "y": 185}, "dragging": false}, {"id": "api_webhook_agent_1781284096335", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "api_webhook_agent", "label": "Webhook", "description": "API Webhook Agent for external system integration", "category": "2", "icon": "Cloud", "badge": "Node", "node_type": "TRIGGER", "id": 9, "version": "1.0.0", "group": null, "color": "#7C3AED", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 99.2558139534884, "y": 132.56976744186045}, "width": 142, "height": 62, "selected": true, "dragging": false}], "edges": [{"type": "smoothstep", "animated": false, "markerEnd": {"type": "arrowclosed", "color": "#981a04ff", "height": 20, "width": 20}, "source": "api_webhook_agent_1781284096335", "sourceHandle": null, "target": "generic_llm_agent_1781210129433", "targetHandle": null, "id": "reactflow__edge-api_webhook_agent_1781284096335-generic_llm_agent_1781210129433", "selected": false}], "entry_point": "input_guard", "is_enabled": true, "updated_at": "2026-06-12T17:08:38.873796"}','2026-06-12T17:08:38.875707',1);
INSERT INTO workflows VALUES('email_processor','Gmail Processor','',1,NULL,'default',NULL,'{"id": "email_processor", "version": "1", "name": "Gmail Processor", "description": "", "category": "default", "nodes_structure": [{"id": "generic_llm_agent_1781251899714", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_llm_agent", "label": "Generic LLM Agent", "description": "Calls an LLM via specific IP and Port using OpenAI-compatible API", "category": "2", "icon": "bot", "badge": "Node", "id": 3, "node_type": "NODE", "version": "1.0.0", "group": null, "color": "#17a2b8", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 450.793023255814, "y": 166.8767441860465}, "width": 189, "height": 62, "selected": false, "positionAbsolute": {"x": 450.793023255814, "y": 166.8767441860465}, "dragging": false}, {"id": "gmail_email_trigger_1781267219334", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "gmail_email_trigger", "label": "IMAP Email Trigger", "description": "Polls an IMAP server for new messages and triggers the workflow.", "category": "4", "icon": "mail", "badge": null, "id": 11, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#EA4335", "sub_label": null, "executionStatus": "idle"}, "position": {"x": 179.07582477014603, "y": 142.66284478096267}, "width": 185, "height": 62, "selected": true, "dragging": false}], "edges": [{"type": "smoothstep", "animated": false, "markerEnd": {"type": "arrowclosed", "color": "#981a04ff", "height": 20, "width": 20}, "source": "gmail_email_trigger_1781267219334", "sourceHandle": null, "target": "generic_llm_agent_1781251899714", "targetHandle": null, "id": "reactflow__edge-gmail_email_trigger_1781267219334-generic_llm_agent_1781251899714", "selected": false}], "entry_point": "input_guard", "is_enabled": true, "updated_at": "2026-06-12T17:07:49.337318"}','2026-06-12T17:07:49.342662',1);
INSERT INTO workflows VALUES('new','new','',1,NULL,'default',NULL,'{"id": "new", "version": "1", "name": "new", "description": "", "category": "default", "nodes_structure": [{"id": "gmail_email_trigger_1781354990348", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "gmail_email_trigger", "label": "Gmail Email Trigger", "description": "Polls an IMAP server for new messages and triggers the workflow.", "category": "4", "icon": "mail", "id": 11, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#EA4335", "sub_label": null, "badge": null, "executionStatus": "idle"}, "position": {"x": -1509.6000000000001, "y": -2820.399999999998}, "width": 190, "height": 62, "selected": true, "positionAbsolute": {"x": -1509.6000000000001, "y": -2820.399999999998}, "dragging": false}, {"id": "context_setter_1781355217334", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "context_setter", "label": "Context Setter", "description": "Enriches input with user context from CRM / DB", "category": "1", "icon": "User", "id": 1, "node_type": "NODE", "version": "1.0.0", "group": null, "color": "#7C3000", "sub_label": "Call any LLM", "badge": "Trigger", "executionStatus": "idle"}, "position": {"x": -1132.6000000000001, "y": -2831.399999999998}, "width": 159, "height": 62, "selected": false, "positionAbsolute": {"x": -1132.6000000000001, "y": -2831.399999999998}, "dragging": false}], "edges": [{"type": "smoothstep", "animated": false, "markerEnd": {"type": "arrowclosed", "color": "#981a04ff", "height": 20, "width": 20}, "source": "gmail_email_trigger_1781354990348", "sourceHandle": null, "target": "context_setter_1781355217334", "targetHandle": null, "id": "reactflow__edge-gmail_email_trigger_1781354990348-context_setter_1781355217334", "selected": false}], "entry_point": "input_guard", "is_enabled": true, "updated_at": "2026-06-13T12:55:02.628565"}','2026-06-13T12:55:02.637235',1);
CREATE TABLE workflow_node_properties (
	id INTEGER NOT NULL, 
	workflow_id VARCHAR NOT NULL, 
	agent_node_id VARCHAR NOT NULL, 
	agent_name VARCHAR, 
	"key" VARCHAR, 
	value VARCHAR, 
	PRIMARY KEY (id)
);
INSERT INTO workflow_node_properties VALUES(13,'scheuler','scheduler_agent_1780940575916','scheduler_agent','interval','10');
INSERT INTO workflow_node_properties VALUES(14,'scheuler','scheduler_agent_1780940575916','scheduler_agent','unit','"seconds"');
INSERT INTO workflow_node_properties VALUES(15,'scheuler','scheduler_agent_1780940575916','scheduler_agent','command','""');
INSERT INTO workflow_node_properties VALUES(16,'scheuler','scheduler_agent_1780940575916','scheduler_agent','targetAgent','""');
INSERT INTO workflow_node_properties VALUES(17,'external_api','api_webhook_agent_1781013883754','api_webhook_agent','property_1780670099641','"9000"');
INSERT INTO workflow_node_properties VALUES(18,'external_api','api_webhook_agent_1781013883754','api_webhook_agent','property_1780670118773','"2"');
INSERT INTO workflow_node_properties VALUES(19,'external_api','api_webhook_agent_1781013883754','api_webhook_agent','workers','"1"');
INSERT INTO workflow_node_properties VALUES(20,'external_api','api_webhook_agent_1781013883754','api_webhook_agent','port','"7777"');
INSERT INTO workflow_node_properties VALUES(21,'test','api_webhook_agent_1781112710869','api_webhook_agent','property_1780670099641','"9000"');
INSERT INTO workflow_node_properties VALUES(22,'test','api_webhook_agent_1781112710869','api_webhook_agent','property_1780670118773','"2"');
INSERT INTO workflow_node_properties VALUES(23,'test','api_webhook_agent_1781112710869','api_webhook_agent','workers','"1"');
INSERT INTO workflow_node_properties VALUES(24,'test','api_webhook_agent_1781112710869','api_webhook_agent','port','"7777"');
INSERT INTO workflow_node_properties VALUES(25,'test','profanity_guard_1781112713321','profanity_guard','enabled','true');
INSERT INTO workflow_node_properties VALUES(26,'test','profanity_guard_1781112713321','profanity_guard','sensitivity','"low"');
INSERT INTO workflow_node_properties VALUES(27,'scheduler','scheduler_agent_1781203597709','scheduler_agent','interval','10');
INSERT INTO workflow_node_properties VALUES(28,'scheduler','scheduler_agent_1781203597709','scheduler_agent','unit','"seconds"');
INSERT INTO workflow_node_properties VALUES(29,'scheduler','scheduler_agent_1781203597709','scheduler_agent','command','""');
INSERT INTO workflow_node_properties VALUES(30,'scheduler','scheduler_agent_1781203597709','scheduler_agent','targetAgent','""');
INSERT INTO workflow_node_properties VALUES(44,'scheuler','generic_llm_agent_1780916465461','generic_llm_agent','ip','"127.0.0.1"');
INSERT INTO workflow_node_properties VALUES(45,'scheuler','generic_llm_agent_1780916465461','generic_llm_agent','port','"11434"');
INSERT INTO workflow_node_properties VALUES(46,'scheuler','generic_llm_agent_1780916465461','generic_llm_agent','model','"qwen:0.5b"');
INSERT INTO workflow_node_properties VALUES(47,'scheuler','generic_llm_agent_1780916465461','generic_llm_agent','temperature','0.7');
INSERT INTO workflow_node_properties VALUES(48,'scheuler','generic_llm_agent_1780916465461','generic_llm_agent','systemPrompt','"analyze the mail content sent and speicify the following \n1- priority - 1-5\n2- possible spam - 1-10\n3- context of the mail - max 50 words\n4- should respond ? yes/no\nreply in json with following fields \n{\"priority\":\"\",\"context\":\"\", \"spam_meter\":\"\", \"respond\":\"\"}"');
INSERT INTO workflow_node_properties VALUES(79,'email_processor','generic_llm_agent_1781251899714','generic_llm_agent','ip','"127.0.0.1"');
INSERT INTO workflow_node_properties VALUES(80,'email_processor','generic_llm_agent_1781251899714','generic_llm_agent','port','"11434"');
INSERT INTO workflow_node_properties VALUES(81,'email_processor','generic_llm_agent_1781251899714','generic_llm_agent','model','"qwen:0.5b"');
INSERT INTO workflow_node_properties VALUES(82,'email_processor','generic_llm_agent_1781251899714','generic_llm_agent','temperature','0.7');
INSERT INTO workflow_node_properties VALUES(83,'email_processor','generic_llm_agent_1781251899714','generic_llm_agent','systemPrompt','"analyze the mail content sent and speicify the following \n1- priority - 1-5\n2- possible spam - 1-10\n3- context of the mail - max 50 words\n4- should respond ? yes/no\nreply in json with following fields \n{\"priority\":\"\",\"context\":\"\", \"spam_meter\":\"\", \"respond\":\"\"}"');
INSERT INTO workflow_node_properties VALUES(84,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','imap_host','"imap.gmail.com"');
INSERT INTO workflow_node_properties VALUES(85,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','imap_port','993');
INSERT INTO workflow_node_properties VALUES(86,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','use_ssl','true');
INSERT INTO workflow_node_properties VALUES(87,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','folder','"INBOX"');
INSERT INTO workflow_node_properties VALUES(88,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','check_interval','60');
INSERT INTO workflow_node_properties VALUES(89,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','mark_as_read','true');
INSERT INTO workflow_node_properties VALUES(90,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','username','"intuact@gmail.com"');
INSERT INTO workflow_node_properties VALUES(91,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','password','"Intuact@123!"');
INSERT INTO workflow_node_properties VALUES(92,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','auth_method','"Gmail OAuth2"');
INSERT INTO workflow_node_properties VALUES(93,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','client_id','"766633200484-v42quiqo5o3evg81ulrcud4np356o7be.apps.googleusercontent.com"');
INSERT INTO workflow_node_properties VALUES(94,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','client_secret','"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"');
INSERT INTO workflow_node_properties VALUES(95,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','refresh_token','"ya29.a0AT3oNZ_vV1JCSUs52zlWectS09NGFN2F-AuGEfK4ryMTP1jZd8736h0oZGeeLBRtK_pryAqfRmfIjqQHE7KWGDpMF4Q2UpOyrpAvbjgJfoeELOLJA5BVaBnrsYUguwaNkMtLAb91j4WpWQ9ky_z3MkvEVBpU-9m1CWlFbKT6c-JK1qXA1m_0GwO1kSzMy07uF8gblI8aCgYKAZISARYSFQHGX2MiwrGFm5NkPzFqiP7TJOSC2w0206"');
INSERT INTO workflow_node_properties VALUES(96,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','webhook_base_url','""');
INSERT INTO workflow_node_properties VALUES(97,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','gmail_topic_name','""');
INSERT INTO workflow_node_properties VALUES(98,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','outlook_subscription_expiration_days','3');
INSERT INTO workflow_node_properties VALUES(99,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','subscription_id','""');
INSERT INTO workflow_node_properties VALUES(100,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','last_processed_email_id','"0"');
INSERT INTO workflow_node_properties VALUES(101,'email','generic_llm_agent_1781210129433','generic_llm_agent','ip','"127.0.0.1"');
INSERT INTO workflow_node_properties VALUES(102,'email','generic_llm_agent_1781210129433','generic_llm_agent','port','"11434"');
INSERT INTO workflow_node_properties VALUES(103,'email','generic_llm_agent_1781210129433','generic_llm_agent','model','"qwen:0.5b"');
INSERT INTO workflow_node_properties VALUES(104,'email','generic_llm_agent_1781210129433','generic_llm_agent','temperature','0.7');
INSERT INTO workflow_node_properties VALUES(105,'email','generic_llm_agent_1781210129433','generic_llm_agent','systemPrompt','"You are a helpful assistant. pls be polite and respond in kind"');
INSERT INTO workflow_node_properties VALUES(106,'email','api_webhook_agent_1781284096335','api_webhook_agent','property_1780670099641','"9000"');
INSERT INTO workflow_node_properties VALUES(107,'email','api_webhook_agent_1781284096335','api_webhook_agent','property_1780670118773','"2"');
INSERT INTO workflow_node_properties VALUES(108,'email','api_webhook_agent_1781284096335','api_webhook_agent','workers','"1"');
INSERT INTO workflow_node_properties VALUES(109,'email','api_webhook_agent_1781284096335','api_webhook_agent','port','"9999"');
INSERT INTO workflow_node_properties VALUES(110,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','credentials','""');
INSERT INTO workflow_node_properties VALUES(111,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','auth','"0"');
INSERT INTO workflow_node_properties VALUES(112,'new','gmail_email_trigger_1781354990348','gmail_email_trigger','auth','"0"');
INSERT INTO workflow_node_properties VALUES(113,'new','context_setter_1781355217334','context_setter','new property','"222"');
INSERT INTO workflow_node_properties VALUES(114,'new','context_setter_1781355217334','context_setter','test2411','"122"');
INSERT INTO workflow_node_properties VALUES(115,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','auth_client_id','"766633200484-v42quiqo5o3evg81ulrcud4np356o7be.apps.googleusercontent.com"');
INSERT INTO workflow_node_properties VALUES(116,'email_processor','gmail_email_trigger_1781267219334','gmail_email_trigger','auth_client_secret','"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"');
INSERT INTO workflow_node_properties VALUES(117,'new','gmail_email_trigger_1781354990348','gmail_email_trigger','auth_client_id','"766633200484-v42quiqo5o3evg81ulrcud4np356o7be.apps.googleusercontent.com"');
INSERT INTO workflow_node_properties VALUES(118,'new','gmail_email_trigger_1781354990348','gmail_email_trigger','auth_client_secret','"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"');
INSERT INTO workflow_node_properties VALUES(119,'new','gmail_email_trigger_1781354990348','gmail_email_trigger','access_token','"ya29.a0AT3oNZ_V_cg8BIt1qU1ssqUkS4J2GJ3_4_2fpbqnq-gvvY5-vLygSYCMwkzz0gYnjePmNIcARPsUFFYd_QViK6LohgNbXpXpQhe6IGRS8vAPfyGiHpwHCDshT4Kmt3_GMPtt80NZR73SbGr4hPyiurBI44Q9eKQnaTYSyO46e0yAAdhh_XtHcjMe7BRA73dtL5JwmXAaCgYKAX8SARYSFQHGX2MiqYyYao6T7lrO1S_zui7EQA0206"');
INSERT INTO workflow_node_properties VALUES(120,'new','gmail_email_trigger_1781354990348','gmail_email_trigger','refresh_token','"1//0gAH0pschaRDTCgYIARAAGBASNwF-L9IrFjX5UidgpHYDHfMhVASgnVg-jDGcZL4T7VLLbMeAf0ao5PVzAPUt2ZSiLDCqZ1ZrsPw"');
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
CREATE INDEX ix_categories_id ON categories (id);
CREATE UNIQUE INDEX ix_categories_group ON categories ("group");
CREATE INDEX ix_nodes_id ON nodes (id);
CREATE UNIQUE INDEX ix_nodes_name ON nodes (name);
CREATE INDEX ix_workflow_nodes_id ON workflow_nodes (id);
CREATE INDEX ix_workflows_id ON workflows (id);
CREATE INDEX ix_workflow_node_properties_key ON workflow_node_properties ("key");
CREATE INDEX ix_workflow_node_properties_agent_node_id ON workflow_node_properties (agent_node_id);
CREATE INDEX ix_workflow_node_properties_id ON workflow_node_properties (id);
CREATE INDEX ix_workflow_node_properties_workflow_id ON workflow_node_properties (workflow_id);
CREATE INDEX ix_workflow_node_properties_agent_name ON workflow_node_properties (agent_name);
CREATE UNIQUE INDEX ix_credentials_name ON credentials (name);
CREATE INDEX ix_credentials_id ON credentials (id);
CREATE UNIQUE INDEX ix_oauth_providers_name ON oauth_providers (name);
CREATE INDEX ix_oauth_providers_id ON oauth_providers (id);
COMMIT;
