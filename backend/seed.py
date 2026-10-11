"""
Seed script — populates the database with realistic demo data.
Run: python seed.py

Demo credentials (not for production):
  admin@example.com    / demo-admin-2024
  legal@example.com    / demo-legal-2024
  compliance@example.com / demo-compliance-2024
  risk@example.com     / demo-risk-2024
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from app.database import SessionLocal
from app.models.user import User
from app.models.regulation import Regulation
from app.models.policy import Policy
from app.models.compliance import Compliance
from app.security import hash_password


def seed():
    db = SessionLocal()
    try:
        # ----------------------------------------------------------------
        # Users
        # ----------------------------------------------------------------
        demo_users = [
            {"email": "admin@example.com",      "full_name": "Admin User",          "role": "admin",              "password": "demo-admin-2024"},
            {"email": "legal@example.com",       "full_name": "Priya M.",            "role": "legal_analyst",      "password": "demo-legal-2024"},
            {"email": "compliance@example.com",  "full_name": "Daniel R.",           "role": "compliance_officer", "password": "demo-compliance-2024"},
            {"email": "risk@example.com",        "full_name": "Arun S.",             "role": "risk_analyst",       "password": "demo-risk-2024"},
        ]

        for u in demo_users:
            if not db.query(User).filter(User.email == u["email"]).first():
                db.add(User(
                    email=u["email"],
                    full_name=u["full_name"],
                    role=u["role"],
                    password_hash=hash_password(u["password"]),
                    is_active=True,
                ))
        db.commit()
        print("✓ Users seeded")

        # ----------------------------------------------------------------
        # Regulations
        # ----------------------------------------------------------------
        regulations_data = [
            {
                "title": "GDPR — General Data Protection Regulation",
                "issuing_authority": "European Parliament",
                "jurisdiction": "European Union",
                "description": "Regulation on the protection of natural persons with regard to the processing of personal data and on the free movement of such data.",
                "status": "Active",
                "effective_date": datetime(2018, 5, 25, tzinfo=timezone.utc),
            },
            {
                "title": "CCPA — California Consumer Privacy Act",
                "issuing_authority": "State of California",
                "jurisdiction": "California, USA",
                "description": "Enhances privacy rights and consumer protection for residents of California.",
                "status": "Active",
                "effective_date": datetime(2020, 1, 1, tzinfo=timezone.utc),
            },
            {
                "title": "HIPAA — Health Insurance Portability and Accountability Act",
                "issuing_authority": "U.S. Congress",
                "jurisdiction": "United States",
                "description": "Provides data privacy and security provisions for safeguarding medical information.",
                "status": "Active",
                "effective_date": datetime(1996, 8, 21, tzinfo=timezone.utc),
            },
            {
                "title": "SOX — Sarbanes-Oxley Act",
                "issuing_authority": "U.S. Congress",
                "jurisdiction": "United States",
                "description": "Sets requirements for all U.S. public company boards, management and public accounting firms.",
                "status": "Active",
                "effective_date": datetime(2002, 7, 30, tzinfo=timezone.utc),
            },
            {
                "title": "ISO 27001 — Information Security Management",
                "issuing_authority": "International Organization for Standardization",
                "jurisdiction": "International",
                "description": "International standard for information security management systems (ISMS).",
                "status": "Active",
                "effective_date": datetime(2022, 10, 25, tzinfo=timezone.utc),
            },
            {
                "title": "PCI DSS — Payment Card Industry Data Security Standard",
                "issuing_authority": "PCI Security Standards Council",
                "jurisdiction": "International",
                "description": "Information security standard for organizations that handle branded credit cards.",
                "status": "Active",
                "effective_date": datetime(2022, 3, 31, tzinfo=timezone.utc),
            },
            {
                "title": "DORA — Digital Operational Resilience Act",
                "issuing_authority": "European Parliament",
                "jurisdiction": "European Union",
                "description": "Regulation on digital operational resilience for the financial sector.",
                "status": "Active",
                "effective_date": datetime(2025, 1, 17, tzinfo=timezone.utc),
            },
            {
                "title": "EU AI Act",
                "issuing_authority": "European Parliament",
                "jurisdiction": "European Union",
                "description": "Regulation laying down harmonised rules on artificial intelligence.",
                "status": "Active",
                "effective_date": datetime(2024, 8, 1, tzinfo=timezone.utc),
            },
            {
                "title": "Basel III — International Banking Regulation",
                "issuing_authority": "Basel Committee on Banking Supervision",
                "jurisdiction": "International",
                "description": "Global regulatory framework for more resilient banks and banking systems.",
                "status": "Active",
                "effective_date": datetime(2023, 1, 1, tzinfo=timezone.utc),
            },
            {
                "title": "ESG Disclosure Requirements",
                "issuing_authority": "SEC / ESRS",
                "jurisdiction": "USA / European Union",
                "description": "Environmental, Social, and Governance disclosure requirements for public companies.",
                "status": "Active",
                "effective_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]

        for r in regulations_data:
            if not db.query(Regulation).filter(Regulation.title == r["title"]).first():
                db.add(Regulation(**r))
        db.commit()
        print("✓ Regulations seeded")

        # ----------------------------------------------------------------
        # Policies
        # ----------------------------------------------------------------
        policies_data = [
            {
                "title": "Information Security Policy",
                "department": "IT & Security",
                "description": "Defines the organization's approach to managing information security risks.",
                "status": "Published",
                "version": "3.2",
                "effective_date": datetime(2024, 1, 15, tzinfo=timezone.utc),
            },
            {
                "title": "Data Retention Policy",
                "department": "Legal & Compliance",
                "description": "Establishes rules for how long different categories of data must be retained.",
                "status": "Under Review",
                "version": "2.1",
                "effective_date": datetime(2023, 6, 1, tzinfo=timezone.utc),
            },
            {
                "title": "Acceptable Use Policy",
                "department": "IT & Security",
                "description": "Governs acceptable use of corporate IT resources, systems, and networks.",
                "status": "Published",
                "version": "4.0",
                "effective_date": datetime(2024, 3, 1, tzinfo=timezone.utc),
            },
            {
                "title": "Vendor Management Policy",
                "department": "Procurement",
                "description": "Defines requirements for assessing, onboarding, and monitoring third-party vendors.",
                "status": "Published",
                "version": "1.5",
                "effective_date": datetime(2023, 9, 1, tzinfo=timezone.utc),
            },
            {
                "title": "Whistleblower Policy",
                "department": "Human Resources",
                "description": "Provides mechanisms for employees to report compliance violations confidentially.",
                "status": "Published",
                "version": "2.0",
                "effective_date": datetime(2023, 1, 1, tzinfo=timezone.utc),
            },
            {
                "title": "AI Usage Policy",
                "department": "Technology",
                "description": "Governs the responsible use of AI systems within the organization.",
                "status": "Draft",
                "version": "0.9",
                "effective_date": None,
            },
            {
                "title": "Business Continuity Policy",
                "department": "Operations",
                "description": "Ensures the organization can continue critical functions during and after a disruption.",
                "status": "Published",
                "version": "2.3",
                "effective_date": datetime(2024, 2, 1, tzinfo=timezone.utc),
            },
        ]

        for p in policies_data:
            if not db.query(Policy).filter(Policy.title == p["title"]).first():
                db.add(Policy(**p))
        db.commit()
        print("✓ Policies seeded")

        # ----------------------------------------------------------------
        # Compliance obligations
        # ----------------------------------------------------------------
        compliance_data = [
            {
                "title": "GDPR — Data Subject Rights",
                "regulation": "GDPR",
                "description": "Implement processes to handle data subject access, deletion, and portability requests within 30 days.",
                "department": "Legal & Compliance",
                "status": "Compliant",
                "risk_level": "High",
                "due_date": datetime(2024, 12, 31, tzinfo=timezone.utc),
            },
            {
                "title": "GDPR — Data Breach Notification",
                "regulation": "GDPR",
                "description": "Notify supervisory authority within 72 hours of becoming aware of a personal data breach.",
                "department": "IT & Security",
                "status": "Compliant",
                "risk_level": "High",
                "due_date": None,
            },
            {
                "title": "HIPAA — PHI Encryption at Rest",
                "regulation": "HIPAA",
                "description": "Encrypt all Protected Health Information stored in databases and file systems.",
                "department": "IT & Security",
                "status": "In Progress",
                "risk_level": "High",
                "due_date": datetime(2024, 9, 30, tzinfo=timezone.utc),
            },
            {
                "title": "SOX — Financial Report Controls",
                "regulation": "SOX",
                "description": "Maintain and test internal controls over financial reporting quarterly.",
                "department": "Finance",
                "status": "Compliant",
                "risk_level": "Medium",
                "due_date": datetime(2024, 12, 31, tzinfo=timezone.utc),
            },
            {
                "title": "PCI DSS — Cardholder Data Environment",
                "regulation": "PCI DSS",
                "description": "Maintain a secure network and systems that process cardholder data.",
                "department": "IT & Security",
                "status": "Non-Compliant",
                "risk_level": "High",
                "due_date": datetime(2024, 8, 31, tzinfo=timezone.utc),
            },
            {
                "title": "DORA — ICT Incident Reporting",
                "regulation": "DORA",
                "description": "Report major ICT-related incidents to financial regulators within required timelines.",
                "department": "Operations",
                "status": "Not Started",
                "risk_level": "Medium",
                "due_date": datetime(2025, 1, 17, tzinfo=timezone.utc),
            },
            {
                "title": "ISO 27001 — Risk Assessment",
                "regulation": "ISO 27001",
                "description": "Conduct annual information security risk assessment and update risk treatment plan.",
                "department": "IT & Security",
                "status": "In Progress",
                "risk_level": "Medium",
                "due_date": datetime(2024, 11, 30, tzinfo=timezone.utc),
            },
            {
                "title": "EU AI Act — High-Risk AI Documentation",
                "regulation": "EU AI Act",
                "description": "Document technical characteristics of all high-risk AI systems before deployment.",
                "department": "Technology",
                "status": "Not Started",
                "risk_level": "High",
                "due_date": datetime(2026, 8, 2, tzinfo=timezone.utc),
            },
        ]

        for c in compliance_data:
            if not db.query(Compliance).filter(Compliance.title == c["title"]).first():
                db.add(Compliance(**c))
        db.commit()
        print("✓ Compliance obligations seeded")

        print("\n✅ Database seeded successfully!")
        print("\nDemo credentials:")
        print("  admin@example.com      / demo-admin-2024")
        print("  legal@example.com      / demo-legal-2024")
        print("  compliance@example.com / demo-compliance-2024")
        print("  risk@example.com       / demo-risk-2024")

    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
