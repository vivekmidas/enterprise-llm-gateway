-- database: ./enterprise_gateway.db

INSERT INTO nodes (
    name, 
    label, 
    description, 
    category, 
    version, 
    icon, 
    color, 
    node_type, 
    property_schema, 
    properties
) VALUES (
    'imap_email_trigger', 
    'IMAP Email Trigger', 
    'Polls an IMAP server for new messages and triggers the workflow.', 
    'Communication', 
    '1.0.0', 
    'mail', 
    '#EA4335', 
    'trigger', 
    '[
        {"key": "imap_host", "label": "IMAP Server", "type": "string", "placeholder": "imap.gmail.com"},
        {"key": "imap_port", "label": "Port", "type": "number", "default": 993},
        {"key": "username", "label": "Email/Username", "type": "string"},
        {"key": "password", "label": "Password / App Password", "type": "password"},
        {"key": "use_ssl", "label": "Use SSL/TLS", "type": "boolean", "default": true},
        {"key": "folder", "label": "Mailbox Folder", "type": "string", "default": "INBOX"},
        {"key": "check_interval", "label": "Poll Interval (sec)", "type": "number", "default": 60},
        {"key": "mark_as_read", "label": "Mark as Seen", "type": "boolean", "default": true}
    ]', 
    '{
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "use_ssl": true,
        "folder": "INBOX",
        "check_interval": 60,
        "mark_as_read": true
    }'
);

