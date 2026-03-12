"""
Web Researcher — Pillar 2: Research Agent ("Digital Credit Manager")
Automatically crawls the web for news, litigation, regulatory developments
related to the company and its promoters.
"""
import os
import re
from typing import List, Dict, Any
from datetime import datetime
from models import ResearchFinding, RiskFlag, FlagColor, FlagCategory
import config


class WebResearcher:
    """Performs automated secondary research via SerpAPI."""

    NEGATIVE_KEYWORDS = [
        "fraud", "scam", "default", "arrest", "money laundering", "cheating",
        "SEBI penalty", "RBI action", "ED raid", "CBI investigation",
        "willful defaulter", "NPA", "insolvency", "NCLT", "winding up",
        "liquidation", "ban", "blacklist", "suspension", "penalty",
        "enforcement directorate", "serious fraud", "SFIO"
    ]

    POSITIVE_KEYWORDS = [
        "growth", "expansion", "award", "profit", "dividend", "upgrade",
        "investment", "partnership", "new plant", "IPO", "rating upgrade",
        "market leader", "innovation", "export", "order book"
    ]

    REGULATORY_KEYWORDS = [
        "RBI regulation", "SEBI circular", "new compliance", "GST amendment",
        "NBFC regulation", "NPA norms", "provision coverage", "Basel III",
        "priority sector", "RERA", "MCA filing"
    ]

    def __init__(self):
        self.api_key = config.SERPAPI_KEY
        self._serpapi = None
        if self.api_key:
            try:
                from serpapi import GoogleSearch
                self._serpapi = GoogleSearch
            except ImportError:
                pass

    def research_company(self, company_name: str, entity_id: str,
                         promoter_names: List[str] = None,
                         sector: str = None, 
                         location: str = None) -> List[ResearchFinding]:
        """Perform comprehensive web research on an entity."""
        promoter_names = promoter_names or []
        findings = []

        # Enhance query context
        context = ""
        if sector and location:
            context = f" {sector} {location}"
        elif sector:
            context = f" {sector}"
        elif location:
            context = f" {location}"

        # 1. Company news
        findings.extend(self._search(
            f'"{company_name}"{context} India news latest',
            entity_id, "company_news"
        ))

        # 2. Promoter background
        if promoter_names:
            for name in promoter_names[:3]:
                findings.extend(self._search(
                    f'"{name}" ("{company_name}" OR promoter OR director) India',
                    entity_id, "promoter"
                ))

        # 3. Litigation and legal
        findings.extend(self._search(
            f'"{company_name}" (litigation OR court case OR "FIR" OR "CBI" OR "ED") India',
            entity_id, "litigation"
        ))

        # 4. Sector-specific risks
        findings.extend(self._search(
            f'"{company_name}" (sector OR industry OR RBI OR regulatory) risk',
            entity_id, "regulatory"
        ))

        # 5. MCA / ROC filings
        findings.extend(self._search(
            f'"{company_name}" (MCA OR ROC filing OR strike off) India',
            entity_id, "mca_filing"
        ))

        return findings

    def _search(self, query: str, entity_id: str, category: str) -> List[ResearchFinding]:
        """Perform a single search query and analyze results."""
        if self._serpapi and self.api_key:
            return self._search_serpapi(query, entity_id, category)
        else:
            return self._search_simulated(query, entity_id, category)

    def _search_serpapi(self, query: str, entity_id: str,
                        category: str) -> List[ResearchFinding]:
        """Search using SerpAPI."""
        try:
            params = {
                "q": query,
                "api_key": self.api_key,
                "engine": "google",
                "gl": "in",  # India
                "hl": "en",
                "num": 5
            }
            search = self._serpapi(params)
            results = search.get_dict()

            findings = []
            for item in results.get("organic_results", [])[:5]:
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")

                sentiment = self._classify_sentiment(title + " " + snippet)
                flags = self._generate_research_flags(title, snippet, sentiment, category)

                findings.append(ResearchFinding(
                    entity_id=entity_id,
                    source=link,
                    title=title,
                    snippet=snippet,
                    sentiment=sentiment,
                    category=category,
                    flags=flags,
                    found_at=datetime.utcnow()
                ))

            return findings
        except Exception as e:
            print(f"SerpAPI error: {e}")
            return self._search_simulated(query, entity_id, category)

    def _search_simulated(self, query: str, entity_id: str,
                          category: str) -> List[ResearchFinding]:
        """Simulated research for demo when SerpAPI is unavailable.
        BUG 2 FIX: Generates company-specific mock articles instead of
        returning identical generic content for every entity.
        """
        # Extract company name from the quoted query string
        company_name = entity_id  # fallback
        match = re.search(r'"([^"]+)"', query)
        if match:
            company_name = match.group(1)

        simulated_results = {
            "company_news": [
                {
                    "title": f"{company_name} reports steady growth in Q3 FY24",
                    "snippet": f"{company_name} reported a 12% increase in revenue driven by strong domestic demand and expansion into new markets.",
                    "source": "https://economictimes.com/news",
                    "sentiment": "positive"
                },
                {
                    "title": f"Sector outlook for {company_name} faces headwinds from new RBI regulations",
                    "snippet": f"New RBI guidelines on NBFC lending may impact growth trajectory for {company_name} and similar mid-sized corporates.",
                    "source": "https://livemint.com/industry",
                    "sentiment": "negative"
                }
            ],
            "litigation": [
                {
                    "title": f"{company_name} — pending case in NCLT Mumbai",
                    "snippet": f"A commercial dispute involving {company_name} with a supplier is pending before NCLT Mumbai bench. The claim amount is under ₹5 Cr.",
                    "source": "https://ecourts.gov.in",
                    "sentiment": "negative"
                }
            ],
            "promoter": [
                {
                    "title": f"{company_name} promoter has 15+ years industry experience",
                    "snippet": f"The managing director of {company_name} has been with the company since inception and holds multiple industry awards for excellence.",
                    "source": "https://linkedin.com",
                    "sentiment": "positive"
                }
            ],
            "regulatory": [
                {
                    "title": f"New GST compliance requirements affecting {company_name}",
                    "snippet": f"E-invoicing threshold lowered to ₹5 Cr turnover. {company_name} must ensure GSTR-2A reconciliation with 3B within 10% threshold.",
                    "source": "https://gst.gov.in",
                    "sentiment": "neutral"
                }
            ],
            "mca_filing": [
                {
                    "title": f"{company_name} annual returns filed on time with ROC",
                    "snippet": f"All statutory filings for {company_name} including AOC-4, MGT-7 are up to date with the Ministry of Corporate Affairs.",
                    "source": "https://mca.gov.in",
                    "sentiment": "positive"
                }
            ]
        }

        results = simulated_results.get(category, simulated_results["company_news"])
        findings = []
        for item in results:
            flags = self._generate_research_flags(
                item["title"], item["snippet"], item["sentiment"], category
            )
            findings.append(ResearchFinding(
                entity_id=entity_id,
                source=item["source"],
                title=item["title"],
                snippet=item["snippet"],
                sentiment=item["sentiment"],
                category=category,
                flags=flags,
                found_at=datetime.utcnow()
            ))

        return findings

    def _classify_sentiment(self, text: str) -> str:
        """Simple rule-based sentiment classification."""
        text_lower = text.lower()
        neg_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw.lower() in text_lower)
        pos_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw.lower() in text_lower)

        if neg_count > pos_count:
            return "negative"
        elif pos_count > neg_count:
            return "positive"
        return "neutral"

    def _generate_research_flags(self, title: str, snippet: str,
                                  sentiment: str, category: str) -> List[RiskFlag]:
        """Generate risk flags from a research finding."""
        flags = []
        combined = (title + " " + snippet).lower()

        if sentiment == "negative":
            # Determine severity
            is_severe = any(kw.lower() in combined for kw in
                          ["fraud", "arrest", "ED", "CBI", "SFIO", "willful defaulter",
                           "money laundering", "scam"])

            if is_severe:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CHARACTER,
                    title=f"Critical: {title[:80]}",
                    description=snippet[:200],
                    source="Web Research"
                ))
            elif "litigation" in combined or "court" in combined or "NCLT" in combined:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CHARACTER,
                    title=f"Litigation: {title[:80]}",
                    description=snippet[:200],
                    source="Web Research — Litigation"
                ))
            elif any(kw.lower() in combined for kw in self.REGULATORY_KEYWORDS):
                flags.append(RiskFlag(
                    color=FlagColor.BLUE, category=FlagCategory.CONDITIONS,
                    title=f"Regulatory: {title[:80]}",
                    description=snippet[:200],
                    source="Web Research — Regulatory"
                ))
            else:
                flags.append(RiskFlag(
                    color=FlagColor.BLUE, category=FlagCategory.CONDITIONS,
                    title=f"Concern: {title[:80]}",
                    description=snippet[:200],
                    source="Web Research"
                ))

        elif sentiment == "positive":
            cat = FlagCategory.CHARACTER if category == "promoter" else FlagCategory.CONDITIONS
            flags.append(RiskFlag(
                color=FlagColor.GREEN, category=cat,
                title=f"Positive: {title[:80]}",
                description=snippet[:200],
                source="Web Research"
            ))

        return flags
