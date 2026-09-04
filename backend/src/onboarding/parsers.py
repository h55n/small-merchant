"""
Multi-format product data parsers.
Handles: CSV, Google Sheets, manual form JSON, product page URL.
All parsers produce List[Dict] → fed into normalizer.
"""
from __future__ import annotations

import io
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# Flexible column name mappings — accepts many variations
COLUMN_MAP: Dict[str, List[str]] = {
    "name": ["name", "product_name", "item", "title", "product", "item_name", "product title", "item name"],
    "price": ["price", "price_inr", "amount", "cost", "mrp", "selling_price", "rate", "price (inr)", "price(inr)", "price (₹)"],
    "description": ["description", "desc", "details", "about", "product_description", "item_description", "product description"],
    "stock": ["stock", "quantity", "qty", "available", "inventory", "stock_count", "units", "available_qty"],
    "category": ["category", "type", "cat", "product_category", "product_type", "department"],
    "product_id": ["product_id", "id", "sku", "item_id", "product id", "sku_code"],
    "return_policy_days": ["return_policy_days", "return_days", "returns", "return_policy", "return_window"],
    "min_order": ["min_order", "min_order_inr", "minimum_order"],
    "max_order": ["max_order", "max_order_inr", "maximum_order"],
}


def _normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Map varied column names to standard names."""
    rename_map = {}
    for std_name, variants in COLUMN_MAP.items():
        for col in df.columns:
            if col.lower().strip() in [v.lower() for v in variants]:
                rename_map[col] = std_name
                break
    return df.rename(columns=rename_map)


def _df_to_raw_products(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert normalized DataFrame to list of raw product dicts."""
    df = _normalize_column_names(df)
    products = []
    for idx, row in df.iterrows():
        product: Dict[str, Any] = {}
        for std_name in COLUMN_MAP.keys():
            if std_name in row.index:
                val = row[std_name]
                if pd.notna(val):
                    product[std_name] = val
                else:
                    product[std_name] = None
            else:
                product[std_name] = None
        product["_source_index"] = idx
        products.append(product)
    return products


# ── CSV Parser ────────────────────────────────────────────────────────────────

def parse_csv(file_content: bytes, encoding: str = "utf-8") -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Parse CSV file content into raw product list.
    Returns (products, error_message). error_message is None on success.
    """
    try:
        # Try multiple encodings
        for enc in [encoding, "utf-8-sig", "latin-1", "iso-8859-1"]:
            try:
                content_str = file_content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return [], "Could not decode file. Ensure it is UTF-8 encoded."

        df = pd.read_csv(io.StringIO(content_str))

        if df.empty:
            return [], "CSV file is empty."

        if len(df.columns) < 2:
            return [], "CSV must have at least 2 columns (name, price)."

        products = _df_to_raw_products(df)
        logger.info(f"CSV parser: extracted {len(products)} raw products")
        return products, None

    except pd.errors.ParserError as e:
        return [], f"CSV parsing error: {str(e)}"
    except Exception as e:
        logger.error(f"CSV parse unexpected error: {e}")
        return [], f"Unexpected error parsing CSV: {str(e)}"


# ── Google Sheets Parser ───────────────────────────────────────────────────────

def parse_google_sheets(sheet_url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Parse Google Sheets URL into raw product list.
    Requires GOOGLE_SHEETS_CREDENTIALS_PATH env var (service account JSON).
    Falls back to public CSV export if credentials not available.
    """
    try:
        sheet_id = _extract_sheet_id(sheet_url)
        if not sheet_id:
            return [], "Invalid Google Sheets URL. Ensure it contains /d/{sheet_id}/."

        # Try service account first
        creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
        if os.path.exists(creds_path):
            try:
                import gspread
                gc = gspread.service_account(filename=creds_path)
                sheet = gc.open_by_key(sheet_id).sheet1
                rows = sheet.get_all_records()
                if not rows:
                    return [], "Sheet appears to be empty."
                df = pd.DataFrame(rows)
                return _df_to_raw_products(df), None
            except Exception as e:
                logger.warning(f"Service account Google Sheets failed: {e}, trying public export")

        # Fallback: public CSV export
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        resp = httpx.get(export_url, timeout=15.0, follow_redirects=True)

        if resp.status_code == 200 and "text/csv" in resp.headers.get("content-type", ""):
            return parse_csv(resp.content)
        elif resp.status_code == 302 or "Sign in" in resp.text[:200]:
            return [], ("Sheet is private. Please share it as 'Anyone with the link can view' "
                       "or provide Google Sheets credentials.")
        else:
            return [], f"Could not access sheet (HTTP {resp.status_code}). Make it publicly viewable."

    except httpx.TimeoutException:
        return [], "Timed out accessing Google Sheets. Check the URL and try again."
    except Exception as e:
        logger.error(f"Google Sheets parse error: {e}")
        return [], f"Error accessing Google Sheets: {str(e)}"


def _extract_sheet_id(url: str) -> Optional[str]:
    """Extract Google Sheets ID from various URL formats."""
    patterns = [
        r"/spreadsheets/d/([a-zA-Z0-9-_]+)",
        r"spreadsheets/d/([a-zA-Z0-9-_]+)",
        r"id=([a-zA-Z0-9-_]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


# ── Manual Form Parser ─────────────────────────────────────────────────────────

def parse_manual_form(products_data: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Parse manually entered product data from UI form.
    Data is already structured — just validate basic shape.
    """
    if not products_data:
        return [], "No products provided."

    if len(products_data) > 200:
        return [], "Maximum 200 products allowed for manual entry."

    raw = []
    for idx, p in enumerate(products_data):
        raw_p: Dict[str, Any] = {
            "name": p.get("name"),
            "price": p.get("price") or p.get("price_inr"),
            "description": p.get("description", ""),
            "stock": p.get("stock") or p.get("stock_count"),
            "category": p.get("category", "Other"),
            "product_id": p.get("product_id"),
            "return_policy_days": p.get("return_policy_days", 0),
            "_source_index": idx,
        }
        raw.append(raw_p)

    logger.info(f"Manual form parser: {len(raw)} products")
    return raw, None


# ── URL Scraper ───────────────────────────────────────────────────────────────

def parse_url(product_page_url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Best-effort product page scraper.
    Returns partial data — merchant must review.
    Works on static HTML; SPAs will yield limited data.
    """
    try:
        from bs4 import BeautifulSoup

        # Validate URL
        if not product_page_url.startswith(("http://", "https://")):
            product_page_url = "https://" + product_page_url

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ProductBot/1.0; +https://razorpay.com)"
        }
        resp = httpx.get(product_page_url, timeout=15.0, follow_redirects=True, headers=headers)

        if resp.status_code != 200:
            return [], f"Could not access URL (HTTP {resp.status_code})."

        soup = BeautifulSoup(resp.text, "lxml")

        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Extract title/name
        name = None
        for selector in ["h1", "title", "[itemprop='name']", ".product-title", ".product-name"]:
            el = soup.select_one(selector)
            if el and el.get_text(strip=True):
                name = el.get_text(strip=True)[:200]
                break

        # Extract price
        price = None
        price_patterns = [
            r"₹\s*([\d,]+\.?\d*)",
            r"Rs\.?\s*([\d,]+\.?\d*)",
            r"INR\s*([\d,]+\.?\d*)",
            r"([\d,]+\.?\d*)\s*INR",
        ]
        page_text = soup.get_text()
        for pattern in price_patterns:
            match = re.search(pattern, page_text)
            if match:
                try:
                    price = float(match.group(1).replace(",", ""))
                    break
                except ValueError:
                    continue

        # Extract description
        description = ""
        for selector in ["meta[name='description']", "[itemprop='description']", ".product-description", ".description", "p"]:
            el = soup.select_one(selector)
            if el:
                if el.name == "meta":
                    description = el.get("content", "")
                else:
                    description = el.get_text(strip=True)
                if len(description) > 20:
                    break
        description = description[:500]

        # Try to find multiple products via structured data
        import json as json_mod
        products = []
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json_mod.loads(script.string or "{}")
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    if item.get("@type") in ("Product", "Offer"):
                        p_name = item.get("name", name or "")
                        p_price = None
                        offers = item.get("offers", {})
                        if isinstance(offers, dict):
                            p_price = offers.get("price")
                        elif isinstance(offers, list) and offers:
                            p_price = offers[0].get("price")
                        if p_name:
                            products.append({
                                "name": str(p_name)[:200],
                                "price": float(p_price) if p_price else price,
                                "description": item.get("description", description)[:500],
                                "stock": None,
                                "category": item.get("category", "Other"),
                                "product_id": None,
                                "return_policy_days": 0,
                                "_source_index": len(products),
                                "_scraped": True,
                            })
            except Exception:
                continue

        # If no structured data found, use page-level extraction
        if not products and name:
            products.append({
                "name": name,
                "price": price,
                "description": description,
                "stock": None,
                "category": "Other",
                "product_id": None,
                "return_policy_days": 0,
                "_source_index": 0,
                "_scraped": True,
            })

        if not products:
            return [], ("Could not extract product data from that URL. "
                       "The page may be JavaScript-rendered (SPA) or require login. "
                       "Try manual entry instead.")

        logger.info(f"URL scraper: extracted {len(products)} products from {product_page_url}")
        return products, None

    except httpx.TimeoutException:
        return [], "Timed out fetching the page. Check the URL and try again."
    except ImportError:
        return [], "URL scraping requires beautifulsoup4. Install: pip install beautifulsoup4 lxml"
    except Exception as e:
        logger.error(f"URL scraper error: {e}")
        return [], f"Error scraping URL: {str(e)}"
