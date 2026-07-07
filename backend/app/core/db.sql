PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

DROP TABLE categories;

CREATE TABLE if not exists categories (
    id INTEGER NOT NULL,
    "group" VARCHAR,
    icon VARCHAR,
    color VARCHAR,
    label VARCHAR,
    description VARCHAR,
    PRIMARY KEY (id)
);

INSERT INTO
    categories
VALUES (
        1,
        'LLM Engines',
        'Brain',
        '#8b5cf6',
        'Large Language Model',
        'Core language model execution points and agent instances'
    );

INSERT INTO
    categories
VALUES (
        2,
        'Safety Guardrails',
        'ShieldAlert',
        '#ef4444',
        'Guard Rails',
        'Real-time validators for safety, compliance, and PII masking.'
    );

INSERT INTO
    categories
VALUES (
        3,
        'External Systems',
        'box',
        '#0A1dde',
        'External Systems',
        'Call external Systems'
    );

INSERT INTO
    categories
VALUES (
        4,
        'Communicaation',
        'mail',
        '#ff000a',
        'Mails',
        'Mails, SMS, WhatsAPP etc..'
    );

INSERT INTO
    categories
VALUES (
        5,
        'Data Operations',
        'database',
        '#06b6d4',
        'Databases',
        'DB queries, API calls, and inline scripts/variable setters.'
    );

INSERT INTO
    categories
VALUES (
        6,
        'Control Logic',
        'gitfork',
        '#f59e0b',
        'Logic',
        'Conditional routers, branching, and data transformations'
    );

INSERT INTO
    categories
VALUES (
        7,
        'Context & Memory',
        'history',
        '#3b82f6',
        'Memory',
        unistr (
            'Chat history managers and context injection helpers.\u0009Context Setter, Session Memory, RAG Embeddings\u000aAlerts\u0009Notifications\u0009Bell\u0009Orange (#f97316)\u0009Integration points for sending logs, emails, or chat alerts.\u0009Slack Notification, Send SMTP Mail, Audit Logger\u000a8. Alignment Implementation Steps\u000aDatabase Migration: Update backend/app/core/db.sql and run a schema migration to seed the categories table with the new IDs, colors, icons, and descriptions matching the grid above.\u000aFrontend Synchronization: Update frontend/app/components/component-categoriees.ts to map the CATEGORIES record to match the backend database labels and icons.\u000aPalette UI Revamp: Adjust the sidebar selector categories to display badges matching the Visual Theme colors for a clean cockpit feeling.\u000a'
        )
    );

INSERT INTO
    categories
VALUES (
        9,
        'Alerts',
        'bell',
        '#f97316',
        'Integration',
        'Integration points for sending logs, emails, or chat alerts.'
    );

INSERT INTO
    categories
VALUES (
        10,
        'Vector Databases',
        'blocks',
        '#10b981',
        'Vector DB',
        'Store and query high-dimensional vector embeddings.'
    );

DROP TABLE credentials;

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

drop table oauth_providers;

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

INSERT INTO
    oauth_providers
VALUES (
        0,
        'google',
        'Google OAuth Provider',
        'Validates and get auth details from Google',
        'http://localhost:3000/api/oauth/google/connect',
        NULL,
        NULL,
        'http://localhost:3000/api/oauth/google/callback',
        NULL
    );

drop table users;

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

INSERT INTO
    users
VALUES (
        1,
        'admin@gateway.com',
        'admin@gateway.com',
        '$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI',
        'test test',
        '0',
        'active',
        'system_admin',
        '2026-06-15T06:54:24.944840',
        '2026-06-15T06:54:24.944863'
    );

INSERT INTO
    users
VALUES (
        2,
        'vivek@midasminds.in',
        'vivek@midasminds.in',
        '$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI',
        'Vivek Jain',
        '1',
        'active',
        'user',
        '2026-06-15T07:02:43.832758',
        '2026-06-15T07:02:43.832776'
    );

INSERT INTO
    users
VALUES (
        5,
        'admin@midasminds.com',
        'admin@midasminds.com',
        '$argon2id$v=19$m=1024,t=2,p=8$/0cgTA2yr5XSuEdFKV0PXA$LtUPEWod7A/RZ6C2Mjs4mPzYvHg53R/huF/R+4vT2xI',
        'Admin',
        '1',
        'active',
        'admin',
        '2026-06-27T16:54:47.398860',
        '2026-06-27T16:54:47.398898'
    );

INSERT INTO
    users
VALUES (
        6,
        'x@test.com',
        'x@test.com',
        '$argon2id$v=19$m=1024,t=2,p=8$Yx05319A/5T52EIuxnluvA$vBKsUmuAFfaOZrc1k2ovDJaD1LKCTsJmXS9yUQtbTfo',
        'x',
        '0',
        'active',
        'admin',
        '2026-06-28T20:06:27.444339',
        '2026-06-28T20:06:27.444361'
    );

INSERT INTO
    users
VALUES (
        7,
        'acme_admin@acme.com',
        'acme_admin@acme.com',
        '$argon2id$v=19$m=1024,t=2,p=8$REeZOKapHltusAwbmrS+jA$J+q741lW6ticcI3QqROUeDv57pXFJInHZqLRZGlwDko',
        'Acme Admin',
        '2',
        'active',
        'admin',
        '2026-07-02T17:17:24.582365',
        '2026-07-02T17:17:24.582370'
    );

INSERT INTO
    users
VALUES (
        8,
        'acme_user@acme.com',
        'acme_user@acme.com',
        '$argon2id$v=19$m=1024,t=2,p=8$mud36oT0WKCu1nge3CPqwA$sQvaFiIZr++gLAAJa5CpasU8lsZa/T6qebOGGhhfp0Q',
        'Acme User',
        '2',
        'active',
        'user',
        '2026-07-02T17:17:24.587579',
        '2026-07-02T17:17:24.587583'
    );

INSERT INTO
    users
VALUES (
        9,
        'other_admin@other.com',
        'other_admin@other.com',
        '$argon2id$v=19$m=1024,t=2,p=8$1oA+SjwGe5bN3zvZOTmfrw$dojOhr5AZOLIlkN0JSoTtxj+VCL36Ct/nX3BWqYXi1w',
        'Other Admin',
        '3',
        'active',
        'admin',
        '2026-07-02T17:17:24.603696',
        '2026-07-02T17:17:24.603703'
    );

INSERT INTO
    users
VALUES (
        10,
        'log_acme_admin@acme.com',
        'log_acme_admin@acme.com',
        '$argon2id$v=19$m=1024,t=2,p=8$oOOVBdtsORLRVE67xIMxfw$Ad65t14OToYpxm+QzHjBdl4JVKhh4gwF0nt7/WBevnA',
        'Acme Log Admin',
        '4',
        'active',
        'admin',
        '2026-07-02T17:17:27.528611',
        '2026-07-02T17:17:27.528615'
    );

INSERT INTO
    users
VALUES (
        11,
        'log_acme_user@acme.com',
        'log_acme_user@acme.com',
        '$argon2id$v=19$m=1024,t=2,p=8$z+LhkMMaRksem+s2a1mRwQ$RSIENwI5JA+wcRcIUdtbcpMjwFavNhCCnZT5H5/W3vs',
        'Acme Log User',
        '4',
        'active',
        'user',
        '2026-07-02T17:17:27.532352',
        '2026-07-02T17:17:27.532355'
    );

INSERT INTO
    users
VALUES (
        12,
        'log_globex_admin@globex.com',
        'log_globex_admin@globex.com',
        '$argon2id$v=19$m=1024,t=2,p=8$7s+JshSruyvs4Z/ClYdqrg$Zs0kr+u0mlOEwFj7vfgyilA5D2+kG7N+vki/mosZ3Eo',
        'Globex Admin',
        '5',
        'active',
        'admin',
        '2026-07-02T17:17:27.542742',
        '2026-07-02T17:17:27.542746'
    );

drop table workflows;

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
    user_id varchar not NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (customer_id) REFERENCES customers (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

INSERT INTO
    workflows
VALUES (
        'external_api',
        'External API',
        '',
        1,
        NULL,
        'default',
        NULL,
        '{"nodes": [{"id": "api_webhook_agent_1782579449688", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "api_webhook_agent", "label": "Base Web hook", "description": "API Webhook Agent for external system integration", "category": "2", "icon": "Cloud", "id": 9, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#7C3AED", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [{"key": "port", "default": "8888"}, {"key": "host", "default": "0.0.0.0"}, {"key": "workers", "default": "1"}], "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "executionStatus": "idle", "variant": "2", "subIcon": "Cloud", "model": "", "properties": {}}, "position": {"x": -166, "y": 93}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "external_api_node_1782579453575", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "external_api_node", "label": "External API", "description": "Calls the third party API ", "category": "1", "icon": "Cloud", "id": 10, "node_type": "NODE", "version": "1.0.0", "group": "", "color": "#5E0CEC", "badge": "Node", "sub_label": "", "user_properties": [{"key": "url", "default": "www.bing.com/search"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "auth_key", "default": ""}, {"key": "path", "default": "/search"}, {"key": "api_path", "default": ""}, {"key": "params", "default": "[{\"q\":\"{{message}}\"}]"}, {"key": "auth_type", "default": "API_KEY"}], "system_properties": [{"key": "host", "default": "www.bing.com"}, {"key": "auth_type", "default": "API_KEY"}], "category_id": 1, "category_color": "#8b5cf6", "is_enabled": true, "executionStatus": "idle", "variant": "1", "subIcon": "Cloud", "model": "", "properties": {"url": "www.bing.com", "protocol": "https", "method": "GET", "auth_key": "", "path": "/search", "api_path": "", "params": "[{\"q\":\"{{message}}\"}]", "auth_type": "API_KEY", "host": "www.bing.com", "mapping_template": "{\n  \"data\": \"{{ input_data.result }}\"\n}"}}, "position": {"x": 306, "y": 86.5}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "api_webhook_agent_1782579449688", "sourceHandle": "source-right", "target": "external_api_node_1782579453575", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__api_webhook_agent_1782579449688source-right-external_api_node_1782579453575target-left", "selected": true}], "entry_point": "input_guard"}',
        '2026-06-27T19:23:56.231205',
        1,
        '1',
        '2'
    );

INSERT INTO
    workflows
VALUES (
        'sentiment_analyis',
        'Sentiment Analyis',
        '',
        1,
        NULL,
        'default',
        NULL,
        '{"nodes": [{"id": "sentiment_analyzer_1782672296380", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "sentiment_analyzer", "label": "Sentiment Analyzer 989", "description": "Analyzes sentiment of user message", "category": "3", "icon": "bot", "id": 8, "node_type": "NODE", "version": "1.0.0", "group": null, "color": "#12239e", "badge": "Node", "sub_label": null, "user_properties": [{"key": "sentiment", "default": "1"}, {"key": "another", "default": "a"}], "system_properties": [{"key": "sentiment", "default": "1"}], "category_id": 3, "category_color": "#0A1dde", "is_enabled": true, "executionStatus": "idle", "variant": "3", "subIcon": "bot", "model": "", "properties": {"sentiment": "1", "another": "a"}}, "position": {"x": 238.5, "y": 88.25}, "measured": {"width": 210, "height": 56}, "selected": true}, {"id": "scheduler_agent_1782935753755", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "scheduler_agent", "label": "Scheduler", "description": "Trigger scheder after n seconds", "category": "2", "icon": "Clock", "id": 7, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#0000CC", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [], "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "executionStatus": "idle", "variant": "2", "subIcon": "Clock", "model": ""}, "position": {"x": -186.75, "y": -25.375}, "measured": {"width": 210, "height": 56}}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "scheduler_agent_1782935753755", "sourceHandle": "source-right", "target": "sentiment_analyzer_1782672296380", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__scheduler_agent_1782935753755source-right-sentiment_analyzer_1782672296380target-left"}], "entry_point": "input_guard"}',
        '2026-07-02T19:00:04.598341',
        0,
        '1',
        '2'
    );

INSERT INTO
    workflows
VALUES (
        'eod_stocks',
        'EOD Stocks',
        '',
        1,
        NULL,
        'default',
        NULL,
        '{"nodes": [{"id": "stocks_api_request_node_1782722681073", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "stocks_api_request_node", "label": "EODHD Stocks", "description": "Calls EODHD for stock details", "category": "1", "icon": "bot", "id": 18, "node_type": "NODE", "version": "1.0.0", "group": "Custom", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [{"key": "auth_key", "default": "", "value": ""}, {"key": "url", "default": "eodhd.com", "value": "eodhd.com"}, {"key": "protocol", "default": "https", "value": "https"}, {"key": "method", "default": "GET", "value": "GET"}, {"key": "params", "default": "api_token=69747bd28b3bd8.99561497&fmt=json", "value": "api_token=69747bd28b3bd8.99561497&fmt=json"}, {"key": "auth_type", "default": "NONE", "value": "NONE"}, {"key": "path", "default": "/api/eod/{{stock_token}}", "value": "/api/eod/{{stock_token}}"}, {"key": "api_path", "default": "", "value": ""}], "category_id": 1, "category_color": "#8b5cf6", "is_enabled": true, "properties": {"auth_key": "", "url": "eodhd.com", "protocol": "https", "method": "GET", "params": "api_token=69747bd28b3bd8.99561497&fmt=json", "auth_type": "NONE", "path": "/api/eod/{{stock_token}}?&fmt={{fmt}}", "api_path": ""}, "executionStatus": "idle", "variant": "1", "subIcon": "bot", "model": ""}, "position": {"x": 359, "y": -307}, "measured": {"width": 210, "height": 55}, "dragging": false, "selected": false}, {"id": "stocks_webhook_agent_1782723972280", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "stocks_webhook_agent", "label": "Stocks Webhook Agent", "description": "Triggers workflows on stock price movements or API alerts", "category": "1", "icon": "bot", "id": 17, "node_type": "TRIGGER", "version": "1.0.0", "group": "Custom", "color": "#2ECC71", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [{"key": "port", "default": "8888"}, {"key": "host", "default": "0.0.0.0"}, {"key": "base_path", "default": "stocks"}], "category_id": 1, "category_color": "#8b5cf6", "is_enabled": true, "properties": {"port": "8888", "host": "0.0.0.0", "base_path": "stocks"}, "executionStatus": "idle", "variant": "1", "subIcon": "bot", "model": ""}, "position": {"x": -17, "y": -148.5}, "measured": {"width": 210, "height": 55}, "dragging": false, "selected": false}, {"id": "generic_mysql_query_executor_1782763274758", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_mysql_query_executor", "label": "MySQL Node", "description": "Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.", "category": "5", "icon": "bot", "id": 20, "node_type": "NODE", "version": "1.0.0", "group": "Data", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": [{"key": "db_port", "default": "531", "value": "531"}, {"key": "db_host", "default": "1", "value": "1"}, {"key": "user_name", "default": "admin", "value": "admin"}, {"key": "password", "default": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", "value": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"}, {"key": "database", "default": "default", "value": "default"}, {"key": "secured", "default": "false", "value": "false"}], "system_properties": [], "category_id": 5, "category_color": "#06b6d4", "is_enabled": true, "executionStatus": "idle", "variant": "5", "subIcon": "bot", "model": "", "properties": {"db_port": "3306", "db_host": "1", "user_name": "admin", "password": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", "database": "default", "secured": "false", "mapping_template": "{\n  \"query_type\": \"INSERT\",\n  \"table_name\": \"stocks_eod\",\n  \"field_values\": \"[{{ input_data.root[].date }},{{ input_data.root[].close }} ]\",\n  \"field_names\": \"[\\\"date\\\",\\\"close\\\"]\"\n}"}}, "position": {"x": 611.5, "y": -23}, "measured": {"width": 210, "height": 55}, "selected": false, "dragging": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "stocks_api_request_node_1782722681073", "sourceHandle": "source-right", "target": "generic_mysql_query_executor_1782763274758", "targetHandle": "target-left", "condition": "failure", "data": {"condition": "failure", "expression": ""}, "id": "xy-edge__stocks_api_request_node_1782722681073source-right-generic_mysql_query_executor_1782763274758target-left", "selected": false, "expression": ""}, {"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "stocks_webhook_agent_1782723972280", "sourceHandle": "source-right", "target": "stocks_api_request_node_1782722681073", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__stocks_webhook_agent_1782723972280source-right-stocks_api_request_node_1782722681073target-left"}], "entry_point": "input_guard"}',
        '2026-06-30T14:18:20.348904',
        1,
        '1',
        '2'
    );

INSERT INTO
    workflows
VALUES (
        'mysql',
        'MySQL',
        '',
        1,
        NULL,
        'default',
        NULL,
        '{"nodes": [{"id": "generic_mysql_query_executor_1782762522453", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_mysql_query_executor", "label": "MySQL Node", "description": "Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.", "category": "5", "icon": "bot", "id": 20, "node_type": "NODE", "version": "1.0.0", "group": "Data", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": [{"key": "db_port", "default": "531", "value": "531"}, {"key": "db_host", "default": "1", "value": "1"}, {"key": "user_name", "default": "admin", "value": "admin"}, {"key": "password", "default": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", "value": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"}, {"key": "database", "default": "default", "value": "default"}, {"key": "secured", "default": "false", "value": "false"}], "system_properties": [], "category_id": 5, "category_color": "#06b6d4", "is_enabled": true, "executionStatus": "idle", "variant": "5", "subIcon": "bot", "model": "", "properties": {"db_port": "3306", "db_host": "1", "user_name": "admin", "password": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", "database": "test", "secured": "false"}}, "position": {"x": 459, "y": -208}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "api_webhook_agent_1782762814888", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "api_webhook_agent", "label": "Base Web hook", "description": "API Webhook Agent for external system integration", "category": "2", "icon": "Cloud", "id": 9, "node_type": "TRIGGER", "version": "1.0.0", "group": null, "color": "#7C3AED", "badge": "Node", "sub_label": null, "user_properties": [{"key": "base_path", "default": "search", "value": "search"}], "system_properties": [{"key": "port", "default": "8888", "value": "8888"}, {"key": "host", "default": "0.0.0.0", "value": "0.0.0.0"}, {"key": "workers", "default": "1", "value": "1"}], "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "properties": {"base_path": "/docs", "port": "8888", "host": "0.0.0.0", "workers": "1"}, "executionStatus": "idle", "variant": "2", "subIcon": "Cloud", "model": ""}, "position": {"x": 34.5, "y": -208}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "profanity_guard_1782991097568", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "profanity_guard", "label": "Profanity Guard", "description": "Profanity and offensive content detection", "category": "2", "icon": "bot", "id": 6, "node_type": "NODE", "version": "1.1.0", "group": null, "color": "#ffb700", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [], "category_id": 2, "category_color": "#ef4444", "is_enabled": true, "executionStatus": "idle", "variant": "2", "subIcon": "bot", "model": ""}, "position": {"x": 427.75, "y": -360.5}, "measured": {"width": 210, "height": 56}, "dragging": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "api_webhook_agent_1782762814888", "sourceHandle": "source-right", "target": "generic_mysql_query_executor_1782762522453", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__api_webhook_agent_1782762814888source-right-generic_mysql_query_executor_1782762522453target-left"}, {"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "api_webhook_agent_1782762814888", "sourceHandle": "source-right", "target": "profanity_guard_1782991097568", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__api_webhook_agent_1782762814888source-right-profanity_guard_1782991097568target-left"}], "entry_point": "input_guard"}',
        '2026-07-02T11:18:54.371887',
        1,
        '1',
        '2'
    );

INSERT INTO
    workflows
VALUES (
        'mysql_webhook',
        'mysql-webhook',
        '',
        1,
        NULL,
        'default',
        NULL,
        '{"nodes": [{"id": "db_webhook_agent_1782909081454", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "db_webhook_agent", "label": "Database Webhook Node", "description": "DB Webhook Agent for DB operations", "category": "5", "icon": "bot", "id": 23, "node_type": "TRIGGER", "version": "1.0.0", "group": "Custom", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": [], "system_properties": [], "category_id": 5, "category_color": "#06b6d4", "is_enabled": true, "properties": {"base_path": "db"}, "executionStatus": "idle", "variant": "5", "subIcon": "bot", "model": ""}, "position": {"x": -77, "y": 117}, "measured": {"width": 210, "height": 56}, "dragging": false, "selected": false}, {"id": "generic_mysql_query_executor_1782915085558", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "generic_mysql_query_executor", "label": "MySQL Node", "description": "Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.", "category": "5", "icon": "bot", "id": 20, "node_type": "NODE", "version": "1.0.0", "group": "Data", "color": "#5E0CEC", "badge": "Node", "sub_label": null, "user_properties": [{"key": "db_port", "default": "3306", "value": "3306"}, {"key": "db_host", "default": "1", "value": "1"}, {"key": "user_name", "default": "admin", "value": "admin"}, {"key": "password", "default": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", "value": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"}, {"key": "database", "default": "test", "value": "test"}, {"key": "secured", "default": "false", "value": "false"}], "system_properties": [], "category_id": 5, "category_color": "#06b6d4", "is_enabled": true, "executionStatus": "idle", "variant": "5", "subIcon": "bot", "model": "", "properties": {"db_port": "3306", "db_host": "1", "user_name": "root", "password": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", "database": "test", "secured": "false"}}, "position": {"x": 296.5, "y": 118.25}, "measured": {"width": 210, "height": 56}, "selected": true, "dragging": false}], "edges": [{"style": {"strokeWidth": 2, "stroke": "#94a3b8"}, "EdgeText": "hello", "markerEnd": {"type": "arrowclosed", "width": 16, "height": 16, "color": "#3208a6b2"}, "source": "db_webhook_agent_1782909081454", "sourceHandle": "source-right", "target": "generic_mysql_query_executor_1782915085558", "targetHandle": "target-left", "condition": "default", "data": {"condition": "default"}, "id": "xy-edge__db_webhook_agent_1782909081454source-right-generic_mysql_query_executor_1782915085558target-left"}], "entry_point": "input_guard"}',
        '2026-07-02T19:03:51.413957',
        1,
        '1',
        '2'
    );

INSERT INTO
    workflows
VALUES (
        'test-relabel-workflow-1',
        'Relabel Test Workflow',
        '',
        1,
        NULL,
        'testing',
        NULL,
        '{"nodes": [{"id": "mysql-1", "type": "custom", "name": null, "config": {}, "next": [], "data": {"name": "mysql_node", "label": "update database with user details", "properties": {}}}], "edges": [], "entry_point": "input_guard"}',
        '2026-07-02T17:16:58.685046',
        1,
        '0',
        '1'
    );

drop table workflow_nodes;

CREATE TABLE IF NOT EXISTS "workflow_nodes" (
    id INTEGER NOT NULL,
    workflow_id VARCHAR NOT NULL,
    agent_node_id VARCHAR,
    description varchar,
    agent_name varchar,
    updated_at VARCHAR,
    properties JSON,
    PRIMARY KEY (id),
    FOREIGN KEY (workflow_id) REFERENCES workflows (id)
);

INSERT INTO
    workflow_nodes
VALUES (
        1,
        'external_api',
        'api_webhook_agent_1782579449688',
        NULL,
        'api_webhook_agent',
        '2026-06-27T19:23:56.231205',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        2,
        'external_api',
        'external_api_node_1782579453575',
        NULL,
        'external_api_node',
        '2026-06-27T19:23:56.231205',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        16,
        'eod_stocks',
        'stocks_api_request_node_1782722681073',
        NULL,
        'stocks_api_request_node',
        '2026-06-30T14:18:20.348904',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        17,
        'eod_stocks',
        'stocks_webhook_agent_1782723972280',
        NULL,
        'stocks_webhook_agent',
        '2026-06-30T14:18:20.348904',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        18,
        'eod_stocks',
        'generic_mysql_query_executor_1782763274758',
        NULL,
        'generic_mysql_query_executor',
        '2026-06-30T14:18:20.348904',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        29,
        'mysql',
        'generic_mysql_query_executor_1782762522453',
        NULL,
        'generic_mysql_query_executor',
        '2026-07-02T11:18:54.371887',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        30,
        'mysql',
        'api_webhook_agent_1782762814888',
        NULL,
        'api_webhook_agent',
        '2026-07-02T11:18:54.371887',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        31,
        'mysql',
        'profanity_guard_1782991097568',
        NULL,
        'profanity_guard',
        '2026-07-02T11:18:54.371887',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        35,
        'test-relabel-workflow-1',
        'mysql-1',
        NULL,
        'mysql_node',
        '2026-07-02T17:16:58.685046',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        38,
        'sentiment_analyis',
        'sentiment_analyzer_1782672296380',
        NULL,
        'sentiment_analyzer',
        '2026-07-02T19:00:04.598341',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        39,
        'sentiment_analyis',
        'scheduler_agent_1782935753755',
        NULL,
        'scheduler_agent',
        '2026-07-02T19:00:04.598341',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        40,
        'mysql_webhook',
        'db_webhook_agent_1782909081454',
        NULL,
        'db_webhook_agent',
        '2026-07-02T19:03:51.413957',
        NULL
    );

INSERT INTO
    workflow_nodes
VALUES (
        41,
        'mysql_webhook',
        'generic_mysql_query_executor_1782915085558',
        NULL,
        'generic_mysql_query_executor',
        '2026-07-02T19:03:51.413957',
        NULL
    );

drop table customers;

CREATE TABLE IF NOT EXISTS "customers" (
    id INTEGER NOT NULL,
    name VARCHAR,
    domain VARCHAR,
    status VARCHAR,
    icon VARCHAR,
    color_schema VARCHAR,
    dateadded VARCHAR not null default CURRENT_TIMESTAMP,
    dateupdated VARCHAR not null default CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

INSERT INTO
    customers
VALUES (
        0,
        'Gateway',
        'gateway.com',
        'active',
        'Building',
        '#ff00ac',
        '2026-06-27T16:51:43.911085',
        '2026-06-27T16:51:43.911109'
    );

INSERT INTO
    customers
VALUES (
        1,
        'midasminds',
        'midasminds',
        'active',
        'Building',
        '#2563eb',
        '2026-06-27T16:51:43.911085',
        '2026-06-27T16:51:43.911109'
    );

INSERT INTO
    customers
VALUES (
        2,
        'Acme Corp',
        'acme.com',
        'active',
        'Building',
        '#ff0000',
        '2026-07-02T17:17:24.564050',
        '2026-07-02T17:17:24.564055'
    );

INSERT INTO
    customers
VALUES (
        3,
        'Other Corp',
        'other.com',
        'active',
        NULL,
        NULL,
        '2026-07-02T17:17:24.592184',
        '2026-07-02T17:17:24.592189'
    );

INSERT INTO
    customers
VALUES (
        4,
        'Log Acme Corp',
        'logacme.com',
        'active',
        NULL,
        NULL,
        '2026-07-02T17:17:27.519483',
        '2026-07-02T17:17:27.519487'
    );

INSERT INTO
    customers
VALUES (
        5,
        'Log Globex',
        'logglobex.com',
        'active',
        NULL,
        NULL,
        '2026-07-02T17:17:27.535020',
        '2026-07-02T17:17:27.535024'
    );

drop table customer_nodes;

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

INSERT INTO
    customer_nodes
VALUES (
        1,
        1,
        'database_node',
        '{}',
        1,
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": false}, {"field_name": "data.p", "field_type": "integer", "required": false}, {"field_name": "auth_token", "field_type": "string", "required": false}, {"field_name": "source_system", "field_type": "string", "required": false}], "additional_fields": true}',
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": false}, {"field_name": "data.chunks", "field_type": "array", "required": false, "items": {"field_type": "string"}}, {"field_name": "data.chunk_count", "field_type": "integer", "required": false}, {"field_name": "data.strategy", "field_type": "string", "required": false}, {"field_name": "data.chunk_size", "field_type": "integer", "required": false}, {"field_name": "data.chunk_overlap", "field_type": "integer", "required": false}, {"field_name": "auth_token", "field_type": "string", "required": false}, {"field_name": "source_system", "field_type": "string", "required": false}]}',
        '2026-07-02T14:03:13.581314',
        'Database'
    );

INSERT INTO
    customer_nodes
VALUES (
        2,
        1,
        'context_setter',
        '{"key": "test2411", "label": "test", "type": "string", "default": "1"}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.584089',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        3,
        1,
        'custom_rule_guard',
        '{"test": "test"}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.586128',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        4,
        1,
        'generic_llm_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.587099',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        5,
        1,
        'output_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.588004',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        6,
        1,
        'presidio_ner_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.588954',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        7,
        1,
        'profanity_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.590115',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        8,
        1,
        'scheduler_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T19:00:04.598341',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        9,
        1,
        'sentiment_analyzer',
        '{"sentiment": "1", "another": "a"}',
        1,
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": false}, {"field_name": "data.chunks", "field_type": "array", "required": false}, {"field_name": "data.chunk_count", "field_type": "integer", "required": false}, {"field_name": "data.strategy", "field_type": "string", "required": false}, {"field_name": "data.chunk_size", "field_type": "integer", "required": false}, {"field_name": "data.chunk_overlap", "field_type": "integer", "required": false}, {"field_name": "auth_token", "field_type": "string", "required": false}, {"field_name": "source_system", "field_type": "string", "required": false}], "additional_fields": true}',
        '{}',
        '2026-07-02T19:00:04.598341',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        10,
        1,
        'api_webhook_agent',
        '{"base_path": "sentiment2", "port": "8888", "host": "0.0.0.0", "workers": "1"}',
        1,
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}',
        '{"result": {"data": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}',
        '2026-07-02T14:03:13.593283',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        11,
        1,
        'external_api_node',
        '{"url": "www.bing.com/search", "protocol": "https", "method": "GET", "auth_key": "", "path": "/search", "api_path": "", "params": "[{\"q\":\"{{message}}\"}]", "auth_type": "API_KEY", "host": "www.bing.com"}',
        1,
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}',
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}',
        '2026-07-02T14:03:13.594243',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        12,
        1,
        'gmail_email_trigger',
        '{"oauth": "oauth", "secret_key": "secret", "secret_value": "value", "client_id": "client", "email_id": "intuact@gmail.com"}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.595128',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        13,
        1,
        'sqlite_query_executor',
        '{"path": "./database.db"}',
        0,
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "object", "required": true}, {"field_name": "data.query_type", "field_type": "string", "required": true}, {"field_name": "data.field_names", "field_type": "array", "required": false}, {"field_name": "data.field_values", "field_type": "array", "required": false}], "additional_fields": true}',
        '{"result": "{{message}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}',
        '2026-07-02T14:03:13.595916',
        'SQLITE'
    );

INSERT INTO
    customer_nodes
VALUES (
        14,
        1,
        'transformer_node',
        '{"x": "x"}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.596640',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        15,
        1,
        'outlook_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.597358',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        16,
        1,
        'stocks_webhook_agent',
        '{"port": "8888", "host": "0.0.0.0", "base_path": "stocks"}',
        1,
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        '{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": false}, {"field_name": "fmt", "field_type": "string", "required": false}, {"field_name": "market", "field_type": "string", "required": false}]}',
        '2026-07-02T14:03:13.597947',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        17,
        1,
        'stocks_api_request_node',
        '{"auth_key": "", "url": "eodhd.com", "protocol": "https", "method": "GET", "params": "api_token=69747bd28b3bd8.99561497&fmt=json", "auth_type": "NONE", "path": "/api/eod/{{stock_token}}", "api_path": ""}',
        1,
        '{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}, {"field_name": "fmt", "field_type": "string", "required": true}], "additional_fields": true}',
        '{"version": "1.0", "rules": [{"field_name": "root[].date", "field_type": "phone", "required": false}, {"field_name": "root[].open", "field_type": "number", "required": false}, {"field_name": "root[].high", "field_type": "number", "required": false}, {"field_name": "root[].low", "field_type": "number", "required": false}, {"field_name": "root[].close", "field_type": "number", "required": false}, {"field_name": "root[].adjusted_close", "field_type": "number", "required": false}, {"field_name": "root[].volume", "field_type": "integer", "required": false}]}',
        '2026-07-02T14:03:13.598658',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        18,
        1,
        'generic_llm_vector_db',
        '{"host": "0.0.0.0.", "port": "6333", "collection": "midas_gateway_docs", "top_k": "5", "api_key": "0", "threshold": "0.7"}',
        1,
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        '{}',
        '2026-07-02T14:03:13.599435',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        19,
        1,
        'generic_mysql_query_executor',
        '{"db_port": "3306", "db_host": "127.0.0.1", "user_name": "root", "password": "password", "database": "test", "secured": "false"}',
        1,
        '{"version": "1.0", "rules": [{"field_name": "query_type", "field_type": "string", "required": false}, {"field_name": "query", "field_type": "string", "required": false}, {"field_name": "table_name", "field_type": "string", "required": false}, {"field_name": "fields", "field_type": "object", "required": false}, {"field_name": "field_names", "field_type": "array", "required": false}, {"field_name": "field_values", "field_type": "array", "required": false}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": "True"}',
        '{"version": "1.0", "rules": [{"field_name": "rowcount", "field_type": "integer", "required": "False"}, {"field_name": "lastrowid", "field_type": "integer", "required": "False"}], "additional_fields": "True"}',
        '2026-07-02T19:09:04.853592',
        'MySQL Node'
    );

INSERT INTO
    customer_nodes
VALUES (
        20,
        1,
        'qdrant_webhook_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.600830',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        21,
        1,
        'text_chunker_node',
        '{"chunking_strategy": "recursive", "chunk_size": 1000, "chunk_overlap": 200, "text": ""}',
        1,
        NULL,
        NULL,
        '2026-07-02T14:03:13.601510',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        22,
        0,
        'generic_llm_vector_db',
        '{"protocol": "", "method": "", "params": "", "auth_type": "", "path": ""}',
        1,
        '{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}',
        '{}',
        '2026-06-29T12:24:12.039229',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        71,
        1,
        'db_webhook_agent',
        '{"base_path": "db"}',
        1,
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        '{}',
        '2026-07-02T19:03:51.413957',
        'Database Webhook Node'
    );

INSERT INTO
    customer_nodes
VALUES (
        72,
        2,
        'database_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609106',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        73,
        2,
        'context_setter',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609111',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        74,
        2,
        'custom_rule_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609113',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        75,
        2,
        'generic_llm_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609114',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        76,
        2,
        'output_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609116',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        77,
        2,
        'presidio_ner_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609117',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        78,
        2,
        'profanity_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609119',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        79,
        2,
        'scheduler_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609120',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        80,
        2,
        'sentiment_analyzer',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609122',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        81,
        2,
        'api_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609123',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        82,
        2,
        'external_api_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609125',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        83,
        2,
        'gmail_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609126',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        84,
        2,
        'sqlite_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609128',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        85,
        2,
        'transformer_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609129',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        86,
        2,
        'outlook_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609131',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        87,
        2,
        'stocks_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609132',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        88,
        2,
        'stocks_api_request_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609134',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        89,
        2,
        'generic_llm_vector_db',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609135',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        90,
        2,
        'generic_mysql_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609137',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        91,
        2,
        'qdrant_webhook_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609138',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        92,
        2,
        'text_chunker_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609140',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        93,
        2,
        'db_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609141',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        94,
        2,
        'dummy_test_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609143',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        95,
        2,
        'dummy_source_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609144',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        96,
        2,
        'dummy_target_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.609146',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        97,
        3,
        'database_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625202',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        98,
        3,
        'context_setter',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625207',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        99,
        3,
        'custom_rule_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625209',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        100,
        3,
        'generic_llm_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625210',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        101,
        3,
        'output_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625212',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        102,
        3,
        'presidio_ner_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625214',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        103,
        3,
        'profanity_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625215',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        104,
        3,
        'scheduler_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625217',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        105,
        3,
        'sentiment_analyzer',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625218',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        106,
        3,
        'api_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625220',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        107,
        3,
        'external_api_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625221',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        108,
        3,
        'gmail_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625223',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        109,
        3,
        'sqlite_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625224',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        110,
        3,
        'transformer_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625225',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        111,
        3,
        'outlook_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625227',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        112,
        3,
        'stocks_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625228',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        113,
        3,
        'stocks_api_request_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625230',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        114,
        3,
        'generic_llm_vector_db',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625232',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        115,
        3,
        'generic_mysql_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625233',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        116,
        3,
        'qdrant_webhook_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625234',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        117,
        3,
        'text_chunker_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625236',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        118,
        3,
        'db_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625237',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        119,
        3,
        'dummy_test_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625239',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        120,
        3,
        'dummy_source_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625241',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        121,
        3,
        'dummy_target_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-01T20:55:11.625242',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        122,
        1,
        'dummy_test_node',
        '{}',
        0,
        NULL,
        NULL,
        '2026-07-02T14:03:13.603181',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        123,
        1,
        'dummy_source_node',
        '{}',
        0,
        NULL,
        NULL,
        '2026-07-02T14:03:13.604738',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        124,
        1,
        'dummy_target_node',
        '{}',
        0,
        NULL,
        NULL,
        '2026-07-02T14:03:13.605432',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        125,
        1,
        'unified_content_guard',
        '{"enable_pii": true, "enable_profanity": true, "enable_custom_keywords": true, "pii_entities": "PHONE_NUMBER, EMAIL_ADDRESS, PERSON, CREDIT_CARD", "score_threshold": 0.6, "additional_profanity_words": "", "additional_sensitive_keywords": "", "filter_mode": "all", "target_fields": "field1, field2"}',
        1,
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        '{}',
        '2026-07-02T18:36:42.505701',
        'Unified Content Guard'
    );

INSERT INTO
    customer_nodes
VALUES (
        126,
        2,
        'database_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568353',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        127,
        2,
        'context_setter',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568359',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        128,
        2,
        'custom_rule_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568361',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        129,
        2,
        'generic_llm_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568363',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        130,
        2,
        'output_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568364',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        131,
        2,
        'presidio_ner_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568366',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        132,
        2,
        'profanity_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568368',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        133,
        2,
        'scheduler_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568369',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        134,
        2,
        'sentiment_analyzer',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568371',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        135,
        2,
        'api_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568372',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        136,
        2,
        'external_api_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568374',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        137,
        2,
        'gmail_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568375',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        138,
        2,
        'sqlite_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568377',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        139,
        2,
        'transformer_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568378',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        140,
        2,
        'outlook_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568380',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        141,
        2,
        'stocks_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568382',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        142,
        2,
        'stocks_api_request_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568383',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        143,
        2,
        'generic_llm_vector_db',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568385',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        144,
        2,
        'generic_mysql_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568386',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        145,
        2,
        'qdrant_webhook_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568388',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        146,
        2,
        'text_chunker_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568389',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        147,
        2,
        'db_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568391',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        148,
        2,
        'unified_content_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.568392',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        149,
        3,
        'database_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594437',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        150,
        3,
        'context_setter',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594441',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        151,
        3,
        'custom_rule_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594443',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        152,
        3,
        'generic_llm_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594445',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        153,
        3,
        'output_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594447',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        154,
        3,
        'presidio_ner_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594448',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        155,
        3,
        'profanity_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594450',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        156,
        3,
        'scheduler_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594452',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        157,
        3,
        'sentiment_analyzer',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594453',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        158,
        3,
        'api_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594455',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        159,
        3,
        'external_api_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594456',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        160,
        3,
        'gmail_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594458',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        161,
        3,
        'sqlite_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594459',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        162,
        3,
        'transformer_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594461',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        163,
        3,
        'outlook_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594462',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        164,
        3,
        'stocks_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594464',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        165,
        3,
        'stocks_api_request_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594466',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        166,
        3,
        'generic_llm_vector_db',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594467',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        167,
        3,
        'generic_mysql_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594469',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        168,
        3,
        'qdrant_webhook_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594470',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        169,
        3,
        'text_chunker_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594472',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        170,
        3,
        'db_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594474',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        171,
        3,
        'unified_content_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:24.594475',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        172,
        4,
        'database_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522246',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        173,
        4,
        'context_setter',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522249',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        174,
        4,
        'custom_rule_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522251',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        175,
        4,
        'generic_llm_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522252',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        176,
        4,
        'output_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522254',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        177,
        4,
        'presidio_ner_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522255',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        178,
        4,
        'profanity_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522257',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        179,
        4,
        'scheduler_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522258',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        180,
        4,
        'sentiment_analyzer',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522260',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        181,
        4,
        'api_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522261',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        182,
        4,
        'external_api_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522263',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        183,
        4,
        'gmail_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522264',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        184,
        4,
        'sqlite_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522266',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        185,
        4,
        'transformer_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522267',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        186,
        4,
        'outlook_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522269',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        187,
        4,
        'stocks_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522270',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        188,
        4,
        'stocks_api_request_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522272',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        189,
        4,
        'generic_llm_vector_db',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522273',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        190,
        4,
        'generic_mysql_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522274',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        191,
        4,
        'qdrant_webhook_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522276',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        192,
        4,
        'text_chunker_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522277',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        193,
        4,
        'db_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522278',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        194,
        4,
        'unified_content_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.522280',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        195,
        5,
        'database_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536963',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        196,
        5,
        'context_setter',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536966',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        197,
        5,
        'custom_rule_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536967',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        198,
        5,
        'generic_llm_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536969',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        199,
        5,
        'output_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536970',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        200,
        5,
        'presidio_ner_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536972',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        201,
        5,
        'profanity_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536973',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        202,
        5,
        'scheduler_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536974',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        203,
        5,
        'sentiment_analyzer',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536976',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        204,
        5,
        'api_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536977',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        205,
        5,
        'external_api_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536978',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        206,
        5,
        'gmail_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536980',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        207,
        5,
        'sqlite_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536986',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        208,
        5,
        'transformer_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536988',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        209,
        5,
        'outlook_email_trigger',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536990',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        210,
        5,
        'stocks_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536991',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        211,
        5,
        'stocks_api_request_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536993',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        212,
        5,
        'generic_llm_vector_db',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536995',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        213,
        5,
        'generic_mysql_query_executor',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536997',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        214,
        5,
        'qdrant_webhook_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.536999',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        215,
        5,
        'text_chunker_node',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.537001',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        216,
        5,
        'db_webhook_agent',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.537002',
        NULL
    );

INSERT INTO
    customer_nodes
VALUES (
        217,
        5,
        'unified_content_guard',
        '{}',
        1,
        NULL,
        NULL,
        '2026-07-02T17:17:27.537004',
        NULL
    );

drop table workflow_node_properties;

CREATE TABLE IF NOT EXISTS "workflow_node_properties" (
    id INTEGER NOT NULL,
    workflow_id VARCHAR NOT NULL,
    agent_node_id VARCHAR NOT NULL,
    agent_name VARCHAR,
    properties JSON,
    label VARCHAR,
    PRIMARY KEY (id),
    FOREIGN KEY (agent_name) REFERENCES nodes (name)
);

INSERT INTO
    workflow_node_properties
VALUES (
        1,
        'external_api',
        'api_webhook_agent_1782579449688',
        'api_webhook_agent',
        '{"base_path":"mysql"}',
        NULL
    );

INSERT INTO
    workflow_node_properties
VALUES (
        2,
        'external_api',
        'external_api_node_1782579453575',
        'external_api_node',
        '{"url": "www.bing.com", "protocol": "https", "method": "GET", "auth_key": "", "path": "/search", "api_path": "", "params": "[{\"q\":\"{{message}}\"}]", "auth_type": "API_KEY", "host": "www.bing.com", "mapping_template": "{\n  \"data\": \"{{ input_data.result }}\"\n}"}',
        NULL
    );

INSERT INTO
    workflow_node_properties
VALUES (
        17,
        'eod_stocks',
        'stocks_api_request_node_1782722681073',
        'stocks_api_request_node',
        '{"auth_key": "", "url": "eodhd.com", "protocol": "https", "method": "GET", "params": "api_token=69747bd28b3bd8.99561497&fmt=json", "auth_type": "NONE", "path": "/api/eod/{{stock_token}}?&fmt={{fmt}}", "api_path": ""}',
        NULL
    );

INSERT INTO
    workflow_node_properties
VALUES (
        18,
        'eod_stocks',
        'stocks_webhook_agent_1782723972280',
        'stocks_webhook_agent',
        '{ "base_path": "stocks"}',
        NULL
    );

INSERT INTO
    workflow_node_properties
VALUES (
        19,
        'eod_stocks',
        'generic_mysql_query_executor_1782763274758',
        'generic_mysql_query_executor',
        '{"db_port": "3306", "db_host": "1", "user_name": "admin", "password": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", "database": "default", "secured": "false", "mapping_template": "{\n  \"query_type\": \"INSERT\",\n  \"table_name\": \"stocks_eod\",\n  \"field_values\": \"[{{ input_data.root[].date }},{{ input_data.root[].close }} ]\",\n  \"field_names\": \"[\\\"date\\\",\\\"close\\\"]\"\n}"}',
        NULL
    );

INSERT INTO
    workflow_node_properties
VALUES (
        30,
        'mysql',
        'generic_mysql_query_executor_1782762522453',
        'generic_mysql_query_executor',
        '{"db_port": "3306", "db_host": "127.0.0.1", "user_name": "admin", "password": "password", "database": "test", "secured": "false"}',
        'MySQL Node'
    );

INSERT INTO
    workflow_node_properties
VALUES (
        31,
        'mysql',
        'api_webhook_agent_1782762814888',
        'api_webhook_agent',
        '{"base_path": "/docs", "port": "8888", "host": "0.0.0.0", "workers": "1"}',
        'Base Web hook'
    );

INSERT INTO
    workflow_node_properties
VALUES (
        32,
        'mysql',
        'profanity_guard_1782991097568',
        'profanity_guard',
        '{}',
        'Profanity Guard'
    );

INSERT INTO
    workflow_node_properties
VALUES (
        39,
        'sentiment_analyis',
        'sentiment_analyzer_1782672296380',
        'sentiment_analyzer',
        '{"sentiment": "1", "another": "a"}',
        'Sentiment Analyzer 989'
    );

INSERT INTO
    workflow_node_properties
VALUES (
        40,
        'sentiment_analyis',
        'scheduler_agent_1782935753755',
        'scheduler_agent',
        '{}',
        'Scheduler'
    );

INSERT INTO
    workflow_node_properties
VALUES (
        41,
        'mysql_webhook',
        'db_webhook_agent_1782909081454',
        'db_webhook_agent',
        '{"base_path": "db"}',
        'Database Webhook Node'
    );

INSERT INTO
    workflow_node_properties
VALUES (
        42,
        'mysql_webhook',
        'generic_mysql_query_executor_1782915085558',
        'generic_mysql_query_executor',
        '{"db_port": "3306", "db_host": "127.0.0.1", "user_name": "root", "password": "password", "database": "test", "secured": "false"}',
        'MySQL Node'
    );

drop table nodes;

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
    PRIMARY KEY (id),
    FOREIGN KEY (category) REFERENCES categories (id)
);

INSERT INTO
    nodes
VALUES (
        0,
        'database_node',
        'Database',
        'NODE',
        'Connects to most common database ',
        '1.0.0',
        '5',
        NULL,
        'database',
        '#772711',
        NULL,
        NULL,
        NULL,
        '[]',
        '[]',
        0,
        NULL
    );

INSERT INTO
    nodes
VALUES (
        1,
        'context_setter',
        'Context Setter',
        'NODE',
        'Enriches input with user context from CRM / DB',
        '1.0.0',
        '1',
        NULL,
        'User',
        '#7C3000',
        'Trigger',
        'Call any LLM',
        '[{"key": "test2411", "label": "test", "type": "string", "default": "1"}]',
        '[]',
        '[{"key": "key", "default": "test2411"}, {"key": "label", "default": "test"}, {"key": "type", "default": "string"}, {"key": "default", "default": "1"}]',
        '{"version": "1.0", "rules": [{"field_name": "user_id", "field_type": "string", "required": true, "min_length": 1, "max_length": 48}], "additional_fields": true}',
        '{"user_id": "", "data": []}'
    );

INSERT INTO
    nodes
VALUES (
        2,
        'custom_rule_guard',
        'Custom Rule',
        'NODE',
        'Dynamic rule-based guard using JSON config',
        '1.0.0',
        '2',
        NULL,
        'bot',
        '#C01010',
        'Node',
        NULL,
        '[]',
        '[]',
        '{"test": "test"}',
        0,
        NULL
    );

INSERT INTO
    nodes
VALUES (
        3,
        'generic_llm_agent',
        'LLM Agent',
        'NODE',
        'Calls an LLM via specific IP and Port using OpenAI-compatible API',
        '1.0.0',
        '1',
        NULL,
        'Brain',
        '#17a2b8',
        'Node',
        'Calls any LLM at the given port with the system prompt',
        '[]',
        '[]',
        '{}',
        '{"version": "1.0", "rules": [{"field_name": "data", "field_type": "json", "required": true}], "additional_fields": true}',
        NULL
    );

INSERT INTO
    nodes
VALUES (
        4,
        'output_guard',
        'Output Guard',
        'NODE',
        'Final safety check - PII leak, MAD, policy compliance',
        '1.0.0',
        '2',
        NULL,
        'bot',
        '#7C3AED',
        'Node',
        NULL,
        '[{"key": "checkPII", "type": "boolean", "label": "Check for PII leaks", "default": true}, {"key": "checkMAD", "type": "boolean", "label": "Check for MAD (Misogyny, Ableism, Discrimination)", "default": true}, {"key": "checkPolicy", "type": "boolean", "label": "Check for custom policy violations", "default": false}]',
        '[]',
        '[]',
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        5,
        'presidio_ner_guard',
        'NER Guard',
        'NODE',
        'Advanced PII + Custom Rules using Presidio',
        '1.1.0',
        '1',
        NULL,
        'bot',
        '#ff6803',
        'Node',
        NULL,
        '[]',
        '[]',
        '[]',
        0,
        NULL
    );

INSERT INTO
    nodes
VALUES (
        6,
        'profanity_guard',
        'Profanity Guard',
        'NODE',
        'Profanity and offensive content detection',
        '1.1.0',
        '2',
        NULL,
        'bot',
        '#ffb700',
        'Node',
        NULL,
        '[{"key": "enabled", "label": "Enabled", "type": "boolean"}, {"key": "sensitivity", "label": "Sensitivity", "type": "choice", "options": ["low", "medium", "high"]}]',
        '[]',
        '[]',
        '{"version": "1.0", "rules": [{"field_name": "id", "field_type": "string", "required": true, "min_length": 1, "max_length": 20, "redact": true}], "additional_fields": true}',
        NULL
    );

INSERT INTO
    nodes
VALUES (
        7,
        'scheduler_agent',
        'Scheduler',
        'TRIGGER',
        'Trigger scheder after n seconds',
        '1.0.0',
        '2',
        NULL,
        'Clock',
        '#0000CC',
        'Node',
        NULL,
        '[]',
        '[]',
        '[]',
        '{"version": "1.0", "rules": [{"field_name": "user_id", "field_type": "json", "required": true}], "additional_fields": true}',
        NULL
    );

INSERT INTO
    nodes
VALUES (
        8,
        'sentiment_analyzer',
        'Sentiment Analyzer',
        'NODE',
        'Analyzes sentiment of user message',
        '1.0.0',
        '3',
        NULL,
        'bot',
        '#12239e',
        'Node',
        NULL,
        '[{"key": "senstivity", "label": "senstivity", "type": "string", "default": ".5"}]',
        '[{"key": "sentiment", "default": "1"}, {"key": "another", "default": "a"}]',
        '[{"key": "sentiment", "default": "1","description":"help"}]',
        0,
        NULL
    );

INSERT INTO
    nodes
VALUES (
        9,
        'api_webhook_agent',
        'Base Web hook',
        'TRIGGER',
        'API Webhook Agent for external system integration',
        '1.0.0',
        '2',
        NULL,
        'Cloud',
        '#7C3AED',
        'Node',
        NULL,
        '[]',
        '[{"key": "base_path", "default": "/docs", "value": "/docs"}]',
        '[{"key": "port", "default": "", "value": ""}, {"key": "host", "default": "", "value": ""}, {"key": "workers", "default": "", "value": ""}]',
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        '{"result": {"data": "{{data}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}}'
    );

INSERT INTO
    nodes
VALUES (
        10,
        'external_api_node',
        'External API',
        'NODE',
        'Calls the third party API ',
        '1.0.0',
        '1',
        '',
        'Cloud',
        '#5E0CEC',
        'Node',
        '',
        '[{"key": "url", "label": "URL", "type": "string", "multiple": false, "default": "0.0.0.0"}, {"key": "path", "label": "path", "type": "string", "default": "/path"}, {"key": "api_path", "label": "api_path", "type": "string", "default": ""}, {"key": "port", "label": "port", "type": "string", "default": "80"}, {"key": "method", "label": "method", "type": "string", "default": "GET"}, {"key": "auth_token", "label": "Auth Token", "type": "string", "default": "-"}, {"key": "protocol", "label": "Protocol", "type": "string", "multiple": false, "default": "HTTP/ HTTPS"}, {"key": "auth_type", "label": "Auth Type", "type": "choice", "default": "[\"DB\",\"Auth_Token\"]"}]',
        '[{"key": "url", "default": "www.bing.com/search"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "auth_key", "default": ""}, {"key": "path", "default": "/search"}, {"key": "api_path", "default": ""}, {"key": "params", "default": "[{\"q\":\"{{message}}\"}]"}, {"key": "auth_type", "default": "API_KEY"}]',
        '[{"key": "host", "default": "www.bing.com"}, {"key": "auth_type", "default": "API_KEY"}]',
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        NULL
    );

INSERT INTO
    nodes
VALUES (
        11,
        'gmail_email_trigger',
        'Gmail',
        'TRIGGER',
        'Polls an IMAP server for new messages and triggers the workflow.',
        '1.0.0',
        '4',
        NULL,
        'mail',
        '#EA4335',
        NULL,
        NULL,
        '[{"key": "auth", "label": "Auth Type", "type": "oauth"}]',
        '[]',
        '{"oauth": "oauth", "secret_key": "secret", "secret_value": "value", "client_id": "client", "email_id": "intuact@gmail.com"}',
        0,
        NULL
    );

INSERT INTO
    nodes
VALUES (
        12,
        'sqlite_query_executor',
        'SQLITE',
        'NODE',
        'Connect to SQLITE Database and execute a query',
        '1.0.0',
        '5',
        '',
        'database',
        '#0624BA',
        'Node',
        '',
        '[{"key": "query_type", "label": "username", "type": "string", "default": ""}, {"key": "field_names", "label": "Field_names", "type": "string", "default": ""}, {"key": "field_values", "label": "Field Values", "type": "string", "default": ""}]',
        '[]',
        '{"path": "./database.db"}',
        '{"data":{"field_names":{"values":[],"mandatory":"True"},"field_values":{"values":[],"mandatory":"True"},"query_type":{"type":"string","mandatory":"True"}}}',
        '{"result": "{{message}}", "error_code": "{{error_code}}", "status": "{{status}}", "error_message": "{{error_message}}"}'
    );

INSERT INTO
    nodes
VALUES (
        13,
        'transformer_node',
        'Data Transformer',
        'NODE',
        'Transforms input data using Jinja2 templates to match the next node''s input',
        '1.0.0',
        '1',
        NULL,
        'shuffle',
        '#c9980b',
        NULL,
        NULL,
        '[{"key": "test", "label": "test", "type": "string", "default": ""}, {"key": "name", "label": "name", "type": "string", "default": ""}]',
        '[]',
        '{"x": "x"}',
        NULL,
        NULL
    );

INSERT INTO
    nodes
VALUES (
        14,
        'outlook_email_trigger',
        'Outlook OAuth Trigger',
        'TRIGGER',
        'Polls Outlook via Microsoft Graph API for new messages.',
        '1.0.0',
        '1',
        'Custom',
        'mail',
        '#EA4335',
        'Node',
        NULL,
        NULL,
        '[]',
        '{}',
        '{}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        17,
        'stocks_webhook_agent',
        'Stocks Webhook Agent',
        'TRIGGER',
        'Triggers workflows on stock price movements or API alerts',
        '1.0.0',
        '1',
        'Custom',
        'bot',
        '#2ECC71',
        'Node',
        NULL,
        NULL,
        '[]',
        '[{"key": "port", "default": "8888"}, {"key": "host", "default": "0.0.0.0"}, {"key": "base_path", "default": "stocks"}]',
        '{"version": "1.0", "rules": [], "additional_fields": true}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        18,
        'stocks_api_request_node',
        'Stocks API',
        'NODE',
        'Calls EODHD for stock details',
        '1.0.0',
        '1',
        'Custom',
        'bot',
        '#5E0CEC',
        'Node',
        NULL,
        NULL,
        '[]',
        '[{"key": "auth_key", "default": ""}, {"key": "url", "default": "eodhd.com"}, {"key": "protocol", "default": "https"}, {"key": "method", "default": "GET"}, {"key": "params", "default": "api_token=69747bd28b3bd8.99561497&fmt=json"}, {"key": "auth_type", "default": "NONE"}, {"key": "path", "default": "/api/eod/{{stock_token}}"}, {"key": "api_path", "default": ""}]',
        '{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        19,
        'generic_llm_vector_db',
        'Store data to VectorDB',
        'NODE',
        'Store data to VectorDB',
        '1.0.0',
        '10',
        'Custom',
        'blocks',
        '#2cb23cff',
        'Node',
        NULL,
        NULL,
        '[{"key": "host", "default": "0.0.0.0", "value": "0.0.0.0"}, {"key": "port", "default": "6333", "value": "6333"}]',
        '{}',
        '{"version": "1.0", "rules": [{"field_name": "stock_token", "field_type": "string", "required": true}], "additional_fields": true}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        20,
        'generic_mysql_query_executor',
        'MySQL Node',
        'NODE',
        'Executes SQL queries on MySQL databases. Supports parameterized queries and Jinja templating.',
        '1.0.0',
        '5',
        'Data',
        'bot',
        '#5E0CEC',
        'Node',
        NULL,
        NULL,
        '[{"key": "db_port", "default": "3306", "value": "3306"}, {"key": "db_host", "default": "127.0.0.1", "value": "1"}, {"key": "user_name", "default": "admin", "value": "admin"}, {"key": "password", "default": "password", "value": "password"}, {"key": "database", "test": "default", "value": "default"}, {"key": "secured", "default": "false", "value": "false"}]',
        '[]',
        '{"version": "1.0", "rules": [{"field_name": "query_type", "field_type": "string", "required": false}, {"field_name": "query", "field_type": "string", "required": false}, {"field_name": "table_name", "field_type": "string", "required": false}, {"field_name": "fields", "field_type": "object", "required": false}, {"field_name": "field_names", "field_type": "array", "required": false}, {"field_name": "field_values", "field_type": "array", "required": false}, {"field_name": "condition", "field_type": "string", "required": false}, {"field_name": "condition_params", "field_type": "array", "required": false}, {"field_name": "params", "field_type": "object", "required": false}], "additional_fields": "True"}',
        '{"version":"1.0","rules":[{"field_name":"rowcount","field_type":"integer","required":"False"},{"field_name":"lastrowid","field_type":"integer","required":"False"}],"additional_fields":"True"}'
    );

INSERT INTO
    nodes
VALUES (
        21,
        'qdrant_webhook_node',
        'Qdrant Webhook Node',
        'TRIGGER',
        'Triggers workflows on Qdrant Vector Database events',
        '1.0.0',
        '1',
        'Custom',
        'bot',
        '#2ECC71',
        'Node',
        NULL,
        NULL,
        '[]',
        '{}',
        '{}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        22,
        'text_chunker_node',
        'Text Chunker',
        'NODE',
        'Splits long text or document content into smaller overlapping chunks.',
        '1.0.0',
        '1',
        'Custom',
        'bot',
        '#06b6d4',
        'Node',
        NULL,
        NULL,
        '{"chunking_strategy": "recursive", "chunk_size": 1000, "chunk_overlap": 200, "text": ""}',
        '{}',
        '{}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        23,
        'db_webhook_agent',
        'Database Webhook Node',
        'TRIGGER',
        'DB Webhook Agent for DB operations',
        '1.0.0',
        '5',
        'Data',
        'bot',
        '#5E0CEC',
        'Node',
        NULL,
        NULL,
        '[{"key": "base_path", "default": "/docs", "value": "/db"}]',
        '[{"key": "base_path", "default": "/docs", "value": "/db"}]',
        '{}',
        '{}'
    );

INSERT INTO
    nodes
VALUES (
        24,
        'unified_content_guard',
        'Unified Content Guard',
        'NODE',
        'Unified safety node filtering PII, profanity, and custom keywords across system, tenant, and workflow scopes.',
        '2.0.0',
        '2',
        'Custom',
        'bot',
        '#D93838',
        'Guard',
        NULL,
        NULL,
        '[{"key": "enable_pii", "label": "Enable PII Redaction", "type": "boolean", "default": true, "description": "Masks personally identifiable information (emails, names, phone numbers)."}, {"key": "enable_profanity", "label": "Enable Profanity Filtering", "type": "boolean", "default": true, "description": "Blocks offensive, inappropriate, and unsafe language."}, {"key": "enable_custom_keywords", "label": "Enable Custom Keywords", "type": "boolean", "default": true, "description": "Redacts user-defined custom keywords."}, {"key": "pii_entities", "label": "PII Entities to Redact", "type": "text", "default": "PHONE_NUMBER, EMAIL_ADDRESS, PERSON, CREDIT_CARD", "description": "Comma-separated list of Presidio entities to detect."}, {"key": "score_threshold", "label": "PII Score Threshold", "type": "number", "default": 0.6, "description": "Confidence score threshold (0.0 to 1.0) for PII detection."}, {"key": "additional_profanity_words", "label": "Additional Profane Words", "type": "textarea", "default": "", "description": "Additional comma-separated profane words to redact."}, {"key": "additional_sensitive_keywords", "label": "Additional Sensitive Keywords", "type": "textarea", "default": "", "description": "Additional comma-separated sensitive keywords to redact."}, {"key": "filter_mode", "label": "Filter Mode", "type": "choice", "options": ["all", "include", "exclude"], "default": "all", "description": "Select whether to scan all fields, target specific fields, or exclude specific fields."}, {"key": "target_fields", "label": "Target Fields", "type": "text", "default": "", "description": "Comma-separated list of target fields to include or exclude (e.g., query, response)."}]',
        '[{"key": "profanity_words_system", "label": "System Baseline Profanities", "type": "textarea", "default": "fuck, shit, asshole, bitch, cunt, bastard", "description": "System-wide baseline profanities (comma-separated)."}, {"key": "sensitive_keywords_system", "label": "System Baseline Keywords", "type": "textarea", "default": "confidential, internal-only, secret", "description": "System-wide baseline sensitive keywords (comma-separated)."}]',
        '{}',
        '{}'
    );

CREATE INDEX ix_categories_id ON categories (id);

CREATE UNIQUE INDEX ix_categories_group ON categories ("group");

CREATE UNIQUE INDEX ix_credentials_name ON credentials (name);

CREATE INDEX ix_credentials_id ON credentials (id);

CREATE UNIQUE INDEX ix_oauth_providers_name ON oauth_providers (name);

CREATE INDEX ix_oauth_providers_id ON oauth_providers (id);

CREATE INDEX ix_users_id ON users (id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE INDEX ix_workflows_id ON workflows (id);

CREATE INDEX ix_workflow_nodes_id ON workflow_nodes (id);

CREATE INDEX ix_customers_id ON customers (id);

CREATE UNIQUE INDEX ix_customers_domain ON customers (domain);

CREATE UNIQUE INDEX ix_customers_name ON customers (name);

CREATE INDEX ix_customer_nodes_id ON customer_nodes (id);

CREATE INDEX ix_customer_nodes_customer_id ON customer_nodes (customer_id);

CREATE INDEX ix_customer_nodes_node_name ON customer_nodes (node_name);

CREATE INDEX ix_workflow_node_properties_agent_node_id ON workflow_node_properties (agent_node_id);

CREATE INDEX ix_workflow_node_properties_id ON workflow_node_properties (id);

CREATE INDEX ix_workflow_node_properties_workflow_id ON workflow_node_properties (workflow_id);

CREATE INDEX ix_workflow_node_properties_agent_name ON workflow_node_properties (agent_name);

CREATE INDEX ix_nodes_id ON nodes (id);

CREATE UNIQUE INDEX ix_nodes_name ON nodes (name);

COMMIT;