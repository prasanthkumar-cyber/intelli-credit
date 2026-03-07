"""
Document Parser — Pillar 1: Data Ingestor
Extracts structured data from PDF documents (Annual Reports, GST filings,
Bank Statements, CIBIL reports, Legal Notices, Sanction Letters).
"""
import re
import os
from typing import Dict, Any, List
from datetime import datetime

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from models import (
    ParsedDocument, DocumentType, RiskFlag, FlagColor, FlagCategory
)


class DocumentParser:
    """Parses uploaded PDF documents and extracts structured financial data."""

    # Indian number format: 1,23,456.78 or 12,34,567
    _AMOUNT_RE = re.compile(r'[\u20b9₹]?\s*([\d,]+(?:\.\d{1,2})?)\s*(?:Cr|Lakh|crore|lakh)?', re.IGNORECASE)

    def parse_pdf(self, filepath: str, entity_id: str, doc_type: str) -> ParsedDocument:
        """Parse a PDF file and extract structured data."""
        text = self._extract_text(filepath)
        filename = os.path.basename(filepath)

        dtype = self._classify_document(doc_type, text)
        extracted = {}
        flags = []

        if dtype == DocumentType.GST_FILING:
            extracted, flags = self._parse_gst(text, entity_id)
        elif dtype == DocumentType.BANK_STATEMENT:
            extracted, flags = self._parse_bank_statement(text, entity_id)
        elif dtype == DocumentType.ANNUAL_REPORT:
            extracted, flags = self._parse_annual_report(text, entity_id)
        elif dtype == DocumentType.CIBIL_REPORT:
            extracted, flags = self._parse_cibil(text, entity_id)
        elif dtype == DocumentType.LEGAL_NOTICE:
            extracted, flags = self._parse_legal_notice(text, entity_id)
        elif dtype == DocumentType.SANCTION_LETTER:
            extracted, flags = self._parse_sanction_letter(text, entity_id)
        elif dtype == DocumentType.BALANCE_SHEET:
            extracted, flags = self._parse_balance_sheet(text, entity_id)
        else:
            extracted = {"raw_text": text[:5000]}

        return ParsedDocument(
            entity_id=entity_id,
            doc_type=dtype,
            filename=filename,
            extracted_data=extracted,
            flags=flags,
            parsed_at=datetime.utcnow()
        )

    def _extract_text(self, filepath: str) -> str:
        """Extract text from PDF using PyMuPDF."""
        if fitz is None:
            return self._fallback_extract(filepath)
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text

    def _fallback_extract(self, filepath: str) -> str:
        """Fallback: read as text if PyMuPDF is unavailable."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return ""

    def _classify_document(self, user_type: str, text: str) -> DocumentType:
        """Classify document type from user hint or content."""
        user_lower = user_type.lower()
        if "gst" in user_lower or "gstr" in user_lower:
            return DocumentType.GST_FILING
        elif "bank" in user_lower:
            return DocumentType.BANK_STATEMENT
        elif "annual" in user_lower or "report" in user_lower:
            return DocumentType.ANNUAL_REPORT
        elif "cibil" in user_lower or "credit" in user_lower:
            return DocumentType.CIBIL_REPORT
        elif "legal" in user_lower or "notice" in user_lower:
            return DocumentType.LEGAL_NOTICE
        elif "sanction" in user_lower:
            return DocumentType.SANCTION_LETTER
        elif "balance" in user_lower:
            return DocumentType.BALANCE_SHEET

        # Auto-detect from content
        text_lower = text.lower()
        if "gstr-3b" in text_lower or "gstr-2a" in text_lower:
            return DocumentType.GST_FILING
        elif "cibil" in text_lower or "credit information" in text_lower:
            return DocumentType.CIBIL_REPORT
        elif "balance sheet" in text_lower:
            return DocumentType.BALANCE_SHEET
        elif "annual report" in text_lower:
            return DocumentType.ANNUAL_REPORT
        return DocumentType.OTHER

    # ──────────── GST Filing Parser ────────────

    def _parse_gst(self, text: str, entity_id: str) -> tuple:
        """Parse GSTR-3B and GSTR-2A data."""
        extracted = {"period": "", "gstr_3b_turnover": 0, "gstr_2a_turnover": 0,
                     "gst_recorded_sales": 0, "total_turnover": 0,
                     "igst": 0, "cgst": 0, "sgst": 0}
        flags = []

        # Extract period
        period_match = re.search(r'(?:period|month|quarter)[:\s]*([\w\-\/]+\d{4})', text, re.I)
        if period_match:
            extracted["period"] = period_match.group(1)

        # GSTR-3B turnover (self-reported)
        gstr3b_match = re.search(r'(?:3B|3-B|self.?reported).*?(?:turnover|taxable|outward)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I | re.DOTALL)
        if gstr3b_match:
            extracted["gstr_3b_turnover"] = self._parse_amount(gstr3b_match.group(1))

        # GSTR-2A turnover (supplier-reported / auto-populated)
        gstr2a_match = re.search(r'(?:2A|2-A|supplier|auto.?populated).*?(?:turnover|inward|purchase)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I | re.DOTALL)
        if gstr2a_match:
            extracted["gstr_2a_turnover"] = self._parse_amount(gstr2a_match.group(1))

        # General turnover
        turnover_match = re.search(r'(?:total|aggregate|gross)\s*(?:turnover|sales)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
        if turnover_match:
            val = self._parse_amount(turnover_match.group(1))
            extracted["total_turnover"] = val
            extracted["gst_recorded_sales"] = val

        # Tax components
        for tax, key in [("IGST", "igst"), ("CGST", "cgst"), ("SGST", "sgst")]:
            match = re.search(rf'{tax}[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
            if match:
                extracted[key] = self._parse_amount(match.group(1))

        # Flag: GSTR-2A vs 3B mismatch
        if extracted["gstr_3b_turnover"] > 0 and extracted["gstr_2a_turnover"] > 0:
            mismatch = abs(extracted["gstr_3b_turnover"] - extracted["gstr_2a_turnover"])
            pct = mismatch / extracted["gstr_3b_turnover"]
            if pct > 0.20:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.GST,
                    title="GSTR-2A vs 3B Major Mismatch",
                    description=f"Discrepancy of {pct:.1%} between self-reported (3B: ₹{extracted['gstr_3b_turnover']:,.0f}) and supplier-reported (2A: ₹{extracted['gstr_2a_turnover']:,.0f}). Possible circular trading or bogus invoicing.",
                    source="GSTR-2A vs 3B Analysis", value=pct * 100,
                    threshold=">20%"
                ))
            elif pct > 0.10:
                flags.append(RiskFlag(
                    color=FlagColor.BLUE, category=FlagCategory.GST,
                    title="GSTR-2A vs 3B Moderate Mismatch",
                    description=f"Discrepancy of {pct:.1%} between 3B and 2A. Needs monitoring.",
                    source="GSTR-2A vs 3B Analysis", value=pct * 100,
                    threshold=">10%"
                ))
            else:
                flags.append(RiskFlag(
                    color=FlagColor.GREEN, category=FlagCategory.GST,
                    title="GSTR-2A and 3B Consistent",
                    description=f"Only {pct:.1%} discrepancy. GST filings are consistent.",
                    source="GSTR-2A vs 3B Analysis", value=pct * 100
                ))

        return extracted, flags

    # ──────────── Bank Statement Parser ────────────

    def _parse_bank_statement(self, text: str, entity_id: str) -> tuple:
        extracted = {"total_credits": 0, "total_debits": 0, "avg_balance": 0,
                     "period": "", "revenue": 0, "bounced_cheques": 0}
        flags = []

        # Credits
        credit_match = re.search(r'(?:total|aggregate)\s*credit[s]?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
        if credit_match:
            extracted["total_credits"] = self._parse_amount(credit_match.group(1))
            extracted["revenue"] = extracted["total_credits"]

        # Debits
        debit_match = re.search(r'(?:total|aggregate)\s*debit[s]?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
        if debit_match:
            extracted["total_debits"] = self._parse_amount(debit_match.group(1))

        # Average balance
        avg_match = re.search(r'(?:average|avg|mean)\s*(?:monthly)?\s*balance[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
        if avg_match:
            extracted["avg_balance"] = self._parse_amount(avg_match.group(1))

        # Bounced cheques
        bounce_match = re.search(r'(?:bounced|returned|dishonour)\s*(?:cheque|check)[s]?[:\s]*(\d+)', text, re.I)
        if bounce_match:
            extracted["bounced_cheques"] = int(bounce_match.group(1))
            if extracted["bounced_cheques"] > 3:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CHARACTER,
                    title="High Cheque Bouncing",
                    description=f"{extracted['bounced_cheques']} cheques bounced. Indicates cash flow stress.",
                    source="Bank Statement", value=extracted["bounced_cheques"]
                ))

        return extracted, flags

    # ──────────── Annual Report Parser ────────────

    def _parse_annual_report(self, text: str, entity_id: str) -> tuple:
        extracted = {"revenue": 0, "ebitda": 0, "net_profit": 0,
                     "total_debt": 0, "total_assets": 0, "net_worth": 0,
                     "operating_margin": 0, "interest_expense": 0}
        flags = []

        patterns = {
            "revenue": r'(?:total\s*)?(?:revenue|income|turnover)\s*(?:from\s*operations)?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "ebitda": r'EBITDA[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "net_profit": r'(?:net\s*)?(?:profit|income)\s*(?:after\s*tax|PAT)?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "total_debt": r'(?:total\s*)?(?:debt|borrowing|liabilit)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "total_assets": r'(?:total\s*)?asset[s]?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "net_worth": r'(?:net\s*worth|shareholders?\s*(?:equity|funds?))[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "interest_expense": r'(?:interest|finance)\s*(?:cost|expense)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.I)
            if match:
                extracted[key] = self._parse_amount(match.group(1))

        # Compute operating margin
        if extracted["revenue"] > 0 and extracted["ebitda"] > 0:
            extracted["operating_margin"] = (extracted["ebitda"] / extracted["revenue"]) * 100

        # Flag: negative net profit
        net_loss = re.search(r'(?:net\s*)?loss[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
        if net_loss:
            loss_val = self._parse_amount(net_loss.group(1))
            extracted["net_profit"] = -loss_val
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CAPACITY,
                title="Net Loss Reported",
                description=f"Company reported net loss of ₹{loss_val:,.0f}",
                source="Annual Report", value=loss_val
            ))

        # Flag: high debt
        if extracted["net_worth"] > 0 and extracted["total_debt"] > 0:
            de_ratio = extracted["total_debt"] / extracted["net_worth"]
            if de_ratio > 3.0:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CAPITAL,
                    title="High Leverage",
                    description=f"Debt/Equity ratio of {de_ratio:.2f}x exceeds safe threshold",
                    source="Annual Report", value=de_ratio, threshold=">3.0x"
                ))

        return extracted, flags

    # ──────────── CIBIL Report Parser ────────────

    def _parse_cibil(self, text: str, entity_id: str) -> tuple:
        extracted = {"cibil_score": 0, "total_credit_facilities": 0,
                     "overdue_accounts": 0, "suit_filed_accounts": 0,
                     "dpd_30_plus": 0, "dpd_90_plus": 0,
                     "credit_utilization_pct": 0}
        flags = []

        # CIBIL score
        score_match = re.search(r'(?:CIBIL|credit)\s*(?:score|rank|rating)[:\s]*(\d{1,3})', text, re.I)
        if score_match:
            score = int(score_match.group(1))
            extracted["cibil_score"] = score
            if score < 600:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CIBIL,
                    title="Poor CIBIL Score",
                    description=f"CIBIL score {score} is below acceptable threshold",
                    source="CIBIL Report", value=score, threshold="<600"
                ))
            elif score >= 750:
                flags.append(RiskFlag(
                    color=FlagColor.GREEN, category=FlagCategory.CIBIL,
                    title="Excellent CIBIL Score",
                    description=f"CIBIL score {score} indicates strong credit history",
                    source="CIBIL Report", value=score
                ))
            else:
                flags.append(RiskFlag(
                    color=FlagColor.BLUE, category=FlagCategory.CIBIL,
                    title="Moderate CIBIL Score",
                    description=f"CIBIL score {score} — acceptable but needs monitoring",
                    source="CIBIL Report", value=score
                ))

        # Overdue accounts
        overdue_match = re.search(r'(?:overdue|default)\s*(?:account|facilit)[:\s]*(\d+)', text, re.I)
        if overdue_match:
            extracted["overdue_accounts"] = int(overdue_match.group(1))
            if extracted["overdue_accounts"] > 0:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CIBIL,
                    title="Overdue Credit Accounts",
                    description=f"{extracted['overdue_accounts']} account(s) with overdue status",
                    source="CIBIL Report", value=extracted["overdue_accounts"]
                ))

        # Suit filed
        suit_match = re.search(r'suit\s*filed[:\s]*(\d+)', text, re.I)
        if suit_match:
            extracted["suit_filed_accounts"] = int(suit_match.group(1))
            if extracted["suit_filed_accounts"] > 0:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CHARACTER,
                    title="Suit Filed by Lenders",
                    description=f"{extracted['suit_filed_accounts']} suit(s) filed against borrower",
                    source="CIBIL Report", value=extracted["suit_filed_accounts"]
                ))

        # DPD
        dpd30 = re.search(r'(?:DPD|days\s*past\s*due)\s*(?:30|thirty)[:\s]*(\d+)', text, re.I)
        if dpd30:
            extracted["dpd_30_plus"] = int(dpd30.group(1))
        dpd90 = re.search(r'(?:DPD|days\s*past\s*due)\s*(?:90|ninety)[:\s]*(\d+)', text, re.I)
        if dpd90:
            extracted["dpd_90_plus"] = int(dpd90.group(1))
            if extracted["dpd_90_plus"] > 0:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CIBIL,
                    title="Severe DPD (90+ days)",
                    description=f"{extracted['dpd_90_plus']} accounts with 90+ days past due",
                    source="CIBIL Report", value=extracted["dpd_90_plus"]
                ))

        return extracted, flags

    # ──────────── Legal Notice Parser ────────────

    def _parse_legal_notice(self, text: str, entity_id: str) -> tuple:
        extracted = {"notice_type": "", "parties": "", "amount_claimed": 0}
        flags = []

        # Amount involved
        amount_match = re.search(r'(?:claim|amount|compensation|damages)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
        if amount_match:
            extracted["amount_claimed"] = self._parse_amount(amount_match.group(1))

        # Check for serious terms
        serious_terms = ["fraud", "embezzlement", "willful default", "money laundering",
                         "securities violation", "insider trading", "SEBI", "ED", "CBI"]
        found = [t for t in serious_terms if t.lower() in text.lower()]
        if found:
            flags.append(RiskFlag(
                color=FlagColor.RED, category=FlagCategory.CHARACTER,
                title="Serious Legal Issues Detected",
                description=f"Legal document mentions: {', '.join(found)}",
                source="Legal Notice Analysis"
            ))
        else:
            flags.append(RiskFlag(
                color=FlagColor.BLUE, category=FlagCategory.CHARACTER,
                title="Legal Notice Detected",
                description="Legal document found — requires manual review of severity",
                source="Legal Notice Analysis"
            ))

        return extracted, flags

    # ──────────── Sanction Letter Parser ────────────

    def _parse_sanction_letter(self, text: str, entity_id: str) -> tuple:
        extracted = {"sanctioned_amount": 0, "interest_rate": 0,
                     "security": "", "conditions": []}
        flags = []

        # Sanctioned amount
        sanction_match = re.search(r'(?:sanction|approved|limit)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)\s*(?:Cr|Lakh|crore)?', text, re.I)
        if sanction_match:
            extracted["sanctioned_amount"] = self._parse_amount(sanction_match.group(1))

        # Interest rate
        rate_match = re.search(r'(?:interest|rate|ROI)[:\s]*(\d+\.?\d*)%', text, re.I)
        if rate_match:
            extracted["interest_rate"] = float(rate_match.group(1))

        flags.append(RiskFlag(
            color=FlagColor.GREEN, category=FlagCategory.CAPACITY,
            title="Existing Sanction from Another Bank",
            description=f"Sanctioned ₹{extracted['sanctioned_amount']:,.0f} at {extracted['interest_rate']}% — validates capacity",
            source="Sanction Letter"
        ))

        return extracted, flags

    # ──────────── Balance Sheet Parser ────────────

    def _parse_balance_sheet(self, text: str, entity_id: str) -> tuple:
        extracted = {"total_assets": 0, "total_liabilities": 0, "net_worth": 0,
                     "current_assets": 0, "current_liabilities": 0,
                     "collateral_value": 0, "retained_earnings": 0}
        flags = []

        patterns = {
            "total_assets": r'(?:total\s*)?asset[s]?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "total_liabilities": r'(?:total\s*)?liabilit[iy](?:es)?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "current_assets": r'(?:current|short.?term)\s*asset[s]?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "current_liabilities": r'(?:current|short.?term)\s*liabilit[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "net_worth": r'(?:net\s*worth|equity)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
            "retained_earnings": r'(?:retained\s*earnings|surplus)[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.I)
            if match:
                extracted[key] = self._parse_amount(match.group(1))

        # Collateral estimate from fixed/tangible assets
        tangible_match = re.search(r'(?:fixed|tangible|property|plant)\s*(?:asset)?[s]?[:\s]*[\u20b9₹]?\s*([\d,]+(?:\.\d+)?)', text, re.I)
        if tangible_match:
            extracted["collateral_value"] = self._parse_amount(tangible_match.group(1))

        # Current ratio flag
        if extracted["current_liabilities"] > 0:
            cr = extracted["current_assets"] / extracted["current_liabilities"]
            if cr < 1.0:
                flags.append(RiskFlag(
                    color=FlagColor.RED, category=FlagCategory.CAPACITY,
                    title="Poor Liquidity",
                    description=f"Current Ratio {cr:.2f} < 1.0 — may struggle to meet short-term obligations",
                    source="Balance Sheet", value=cr, threshold="<1.0"
                ))
            elif cr >= 1.5:
                flags.append(RiskFlag(
                    color=FlagColor.GREEN, category=FlagCategory.CAPACITY,
                    title="Strong Liquidity",
                    description=f"Current Ratio {cr:.2f} indicates healthy short-term position",
                    source="Balance Sheet", value=cr
                ))

        return extracted, flags

    # ──────────── Helpers ────────────

    def _parse_amount(self, s: str) -> float:
        """Parse Indian-format amounts: 1,23,456.78"""
        try:
            return float(s.replace(",", ""))
        except (ValueError, TypeError):
            return 0.0
