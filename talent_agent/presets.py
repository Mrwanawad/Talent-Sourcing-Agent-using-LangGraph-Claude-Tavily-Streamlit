"""Real estate hiring presets for the UI: common roles, Egypt/Gulf locations, developers and brokerages."""

from __future__ import annotations

ROLE_PRESETS: dict[str, dict] = {
    "Sales Team Lead": {
        "seniority": "lead",
        "min_years": 5,
        "must": ["real estate sales", "team leadership", "CRM"],
        "nice": ["proptech", "Arabic and English", "off-plan launches"],
    },
    "Property Consultant": {
        "seniority": "mid",
        "min_years": 2,
        "must": ["real estate sales", "client relationships", "negotiation"],
        "nice": ["resale", "off-plan", "Arabic and English"],
    },
    "Sales Manager": {
        "seniority": "manager",
        "min_years": 8,
        "must": ["real estate sales", "sales team management", "sales targets"],
        "nice": ["CRM", "developer launches", "broker networks"],
    },
    "Sales Director": {
        "seniority": "director",
        "min_years": 12,
        "must": ["real estate sales", "sales strategy", "managing sales managers"],
        "nice": ["developer partnerships", "P&L ownership"],
    },
    "Leasing / Rental Agent": {
        "seniority": "mid",
        "min_years": 2,
        "must": ["leasing", "property viewings", "negotiation"],
        "nice": ["short-term rentals", "property management"],
    },
    "Real Estate Marketing Manager": {
        "seniority": "manager",
        "min_years": 6,
        "must": ["real estate marketing", "digital campaigns", "lead generation"],
        "nice": ["project launches", "performance marketing"],
    },
    "After-Sales / Customer Success": {
        "seniority": "mid",
        "min_years": 3,
        "must": ["after-sales", "customer service", "real estate"],
        "nice": ["handover", "contracts and installments"],
    },
    "Mortgage Advisor": {
        "seniority": "mid",
        "min_years": 3,
        "must": ["mortgage", "property financing", "banking"],
        "nice": ["credit assessment", "real estate"],
    },
}

LOCATIONS = [
    "Cairo, Egypt",
    "New Cairo, Egypt",
    "Sheikh Zayed, Egypt",
    "6th of October, Egypt",
    "New Administrative Capital, Egypt",
    "North Coast, Egypt",
    "Alexandria, Egypt",
    "Dubai, UAE",
    "Riyadh, Saudi Arabia",
]

DEVELOPERS = [
    "Palm Hills",
    "SODIC",
    "Emaar Misr",
    "Mountain View",
    "Ora Developers",
    "Hyde Park",
    "Tatweer Misr",
    "Madinet Masr",
    "Talaat Moustafa Group",
    "Hassan Allam Properties",
    "La Vista",
    "Misr Italia",
]

BROKERAGES = ["Coldwell Banker", "RE/MAX", "The Address Investments", "Red Brick", "Bold Routes"]
