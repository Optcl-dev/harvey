"""Optcl High-Intent Lead Identification Test Run.

Prospects commercial real estate developers & asset managers across target DACH hubs,
profiles their websites, extracts decision-makers and intent signals, scores them
against Optcl's ICP, and records them in the database.
Zero emails staged or sent.
"""

import asyncio
import logging
import sys

from harvey.agents.scout import Scout
from harvey.brain import Brain
from harvey.config import load_config, load_env
from harvey.state import StateManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("optcl.test_run")


async def main():
    print("\n" + "=" * 70)
    print("  OPTCL HIGH-INTENT LEAD IDENTIFICATION TEST RUN")
    print("  Target ICP: Commercial Developers, Bauträger & Asset Managers (DACH)")
    print("=" * 70)

    config = load_config()
    env = load_env()
    state = StateManager()
    brain = Brain(state)
    scout = Scout(brain=brain, state=state, config=config, env=env)

    target_queries = [
        "Projektentwickler Gewerbeimmobilien Köln",
        "Gewerbeimmobilien Projektentwicklung Düsseldorf",
    ]

    print(f"\n[1] Discovering Commercial Real Estate Developers...")
    discovered_companies = []
    seen_domains = set()

    for q in target_queries:
        print(f"  → Search: '{q}'")
        results = await scout._web_search(q)
        for url, snippet in results:
            domain = scout._extract_domain(url)
            if not domain or domain in seen_domains:
                continue
            if scout._is_noise_domain(domain):
                continue
            seen_domains.add(domain)
            name = scout._domain_to_name(domain)
            discovered_companies.append({
                "name": name,
                "domain": domain,
                "website": f"https://{domain}",
                "snippet": snippet,
            })

    print(f"\n[2] Qualified {len(discovered_companies)} commercial real estate domains.")
    print("-" * 70)

    high_intent_leads = []

    for idx, c in enumerate(discovered_companies[:5], start=1):
        domain = c["domain"]
        print(f"\n[{idx}/5] Profiling: {c['name']} ({domain})")

        # 1. Store / Ensure company record
        company_id = await scout._ensure_company(
            name=c["name"],
            domain=domain,
            website=c["website"],
            description=c["snippet"],
            industry="Commercial Real Estate",
            source="optcl_scout",
            source_url=c["website"],
        )

        # 2. Extract technical and hiring signals
        signal_note = ""
        try:
            signal_note = await scout._enrich_company_signals(company_id, domain)
            if signal_note:
                print(f"      Signals: {signal_note}")
        except Exception as e:
            logger.debug(f"Signal enrichment error: {e}")

        # 3. Extract team / decision-makers
        contacts = []
        try:
            contacts = await scout._contacts_from_company(
                company_id=company_id,
                domain=domain,
                company_name=c["name"],
                industry="Commercial Real Estate",
                signal_note=signal_note,
                source="company_website",
            )
        except Exception as e:
            logger.debug(f"Contact extraction error: {e}")

        # 4. Score and persist prospects
        persisted_contacts = []
        for ct in contacts:
            ct.score = scout._heuristic_score(ct)
            # Seniority & title bonus for German C-Suite
            if any(t in ct.title.lower() for t in ["geschäftsführer", "inhaber", "vorstand", "partner"]):
                ct.score = max(ct.score, 85)
            await state.add_prospect(ct)
            persisted_contacts.append(ct)
            print(f"      Decision-Maker: {ct.full_name()} [{ct.title}] — ICP Intent Score: {ct.score}/100")

        stored_co = await state.get_company(company_id)
        tech_list = stored_co.tech_stack if stored_co else []

        high_intent_leads.append({
            "company": c["name"],
            "domain": domain,
            "website": c["website"],
            "snippet": c["snippet"],
            "signals": signal_note,
            "tech_stack": tech_list,
            "contacts": persisted_contacts,
        })

    # Summary Report
    print("\n" + "=" * 70)
    print("  EXECUTIVE SUMMARY: IDENTIFIED HIGH-INTENT TARGET LEADS")
    print("=" * 70)

    for i, lead in enumerate(high_intent_leads, start=1):
        print(f"\n{i}. {lead['company'].upper()} ({lead['domain']})")
        print(f"   • Website: {lead['website']}")
        if lead['tech_stack']:
            print(f"   • Tech Stack Detected: {', '.join(lead['tech_stack'])}")
        if lead['signals']:
            print(f"   • Intent Signals: {lead['signals']}")
        print(f"   • Overview: {lead['snippet'][:160]}...")

        if lead['contacts']:
            print(f"   • Identified Decision-Makers:")
            for ct in lead['contacts']:
                email_info = f"Email: {ct.email} ({ct.email_status})" if ct.email else "Email: To be verified"
                print(f"     - {ct.full_name()} | Title: {ct.title} | {email_info} | ICP Fit Score: {ct.score}/100")
        else:
            print("   • Leadership: Routed via corporate contact desk / Impressum")

    print("\n" + "=" * 70)
    print("  TEST RUN COMPLETE — DATA SAVED TO data/harvey.db (0 EMAILS SENT)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
