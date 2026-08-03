"""
Legal domain field definitions.

Keep this list deliberately small. It defines what is important, not what
must exist in every case.
"""

LEGAL_FIELDS = {
    "case_identity": {
        "court": "Court or tribunal name",
        "location": "Court location / jurisdiction if explicitly available",
        "case_number": "Primary case number",
        "report_number": "Report / reference number if present",
        "case_date": "Date of the judgment/order/case document",
        "judge": "Judge, justice, bench or coram",
    },
    "parties": {
        "petitioners": "Petitioner(s), applicant(s), claimant(s) or equivalent",
        "respondents": "Respondent(s), opponent(s), defendant(s) or equivalent",
        "appellants": "Appellant(s), if applicable",
        "other_parties": "Other materially identified parties and their roles",
    },
    "substance": {
        "issues": "Material legal issues expressly raised or decided",
        "facts": "Material facts stated in the document",
        "arguments": "Material arguments/positions expressly attributed to a party",
        "statutes": "Statutes, regulations and provisions expressly cited",
        "precedents": "Cases/authorities expressly cited",
    },
    "decision": {
        "disposition": "Outcome/order/disposition expressly stated",
        "holding": "Holding or legal conclusion, if stated",
        "relief": "Relief granted/refused/ordered, if stated",
    },
}
