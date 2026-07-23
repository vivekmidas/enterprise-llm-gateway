"""
NOT A NEW NODE.

Use existing node: gemini_node (or generic_llm_agent)
Configure user_properties.system_prompt with the CV metadata extraction prompt.

Prompt template (set in workflow node user_properties):

  You are an HR data extraction assistant. Extract the following fields from the
  CV text and return ONLY a valid JSON object — no markdown, no explanation:
  {
    "applicant_name": string,
    "email": string,
    "phone": string,
    "current_position": string,
    "current_company": string,
    "experience_years": integer,
    "skills": [string],
    "education": string,
    "certifications": [string],
    "languages": [string],
    "location": string,
    "linkedin": string,
    "summary": string,
    "doc_type": "cv"
  }
  Use empty string or [] for missing fields. Never invent data.

temperature = 0.0
max_tokens  = 1024

This file is kept for documentation only and is NOT imported by the registry.
"""
