"""
PokeAlert UK — Email Templates
================================
All templates return (subject: str, html: str).
Uses dark theme inline CSS compatible with major email clients.
"""

# ── Shared styles ─────────────────────────────────────────────
_BASE_STYLES = """
  body, table, td { margin: 0; padding: 0; font-family: -apple-system, 'Segoe UI', Arial, sans-serif; }
  body { background-color: #0a0a0f; color: #e8e8f0; -webkit-text-size-adjust: 100%; }
  table { border-collapse: collapse; }
  a { color: #FFD700; text-decoration: none; }
  a:hover { text-decoration: underline; }
""".strip()

_FOOTER_STYLES = "font-size: 12px; color: #6b6b80; text-align: center; padding: 24px 0; border-top: 1px solid #2a2a3a;"


def _wrap(content: str, unsubscribe_url: str) -> str:
    """Wrap content in the shared email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PokeAlert UK</title>
<style>{_BASE_STYLES}</style>
</head>
<body bgcolor="#0a0a0f">
  <table width="100%" bgcolor="#0a0a0f" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding: 40px 16px;">
        <table width="600" style="max-width: 600px; width: 100%;" cellpadding="0" cellspacing="0">

          <!-- Header -->
          <tr>
            <td style="background: #12121a; border: 1px solid #2a2a3a; border-radius: 12px 12px 0 0; padding: 28px 32px; border-bottom: 2px solid #FFD700;">
              <span style="font-size: 22px; font-weight: 700; letter-spacing: 2px; color: #FFD700;">POKEALERT UK</span>
              <span style="font-size: 12px; color: #6b6b80; margin-left: 12px; letter-spacing: 1px;">POKÉMON TCG TRACKER</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background: #12121a; border: 1px solid #2a2a3a; border-top: none; padding: 32px;">
              {content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background: #0d0d14; border: 1px solid #2a2a3a; border-top: none; border-radius: 0 0 12px 12px; padding: 20px 32px;">
              <p style="{_FOOTER_STYLES}">
                PokeAlert UK — fan-made Pokémon TCG tracker&nbsp;&nbsp;|&nbsp;&nbsp;
                <a href="{unsubscribe_url}" style="color: #6b6b80; text-decoration: underline;">Unsubscribe</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _cta_button(label: str, url: str) -> str:
    return (
        f'<table cellpadding="0" cellspacing="0" style="margin: 24px 0;">'
        f'<tr><td style="background: #FFD700; border-radius: 6px; padding: 0;">'
        f'<a href="{url}" style="display: inline-block; padding: 14px 28px; font-size: 15px; '
        f'font-weight: 700; color: #0a0a0f; letter-spacing: 1px; text-decoration: none;">{label}</a>'
        f'</td></tr></table>'
    )


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display: inline-block; background: {color}22; color: {color}; '
        f'border: 1px solid {color}55; border-radius: 4px; padding: 3px 10px; '
        f'font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;">'
        f'{text}</span>'
    )


# ── 1. Welcome / Confirmation ──────────────────────────────────
def welcome_email(unsubscribe_url: str) -> tuple[str, str]:
    subject = "You're in — PokeAlert UK is watching for you 🎴"
    content = f"""
      <h1 style="font-size: 28px; font-weight: 800; color: #e8e8f0; margin: 0 0 8px;">
        You're on the list.
      </h1>
      <p style="font-size: 15px; color: #6b6b80; margin: 0 0 28px; line-height: 1.5;">
        PokeAlert UK will send you real-time alerts whenever something changes at UK retailers.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" style="background: #1a1a26; border: 1px solid #2a2a3a; border-radius: 8px; margin-bottom: 28px;">
        <tr>
          <td style="padding: 20px 24px;">
            <p style="font-size: 13px; font-weight: 700; color: #FFD700; letter-spacing: 1px; margin: 0 0 16px; text-transform: uppercase;">What you'll get</p>
            <table cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #2a2a3a; font-size: 14px; color: #e8e8f0;">
                  🔔 &nbsp;<strong>Pre-order alerts</strong>
                  <span style="color: #6b6b80; font-size: 13px; display: block; margin-left: 28px; margin-top: 2px;">
                    The moment pre-orders open at any UK retailer
                  </span>
                </td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #2a2a3a; font-size: 14px; color: #e8e8f0;">
                  📦 &nbsp;<strong>Back in stock alerts</strong>
                  <span style="color: #6b6b80; font-size: 13px; display: block; margin-left: 28px; margin-top: 2px;">
                    When sold-out sets come back at any retailer
                  </span>
                </td>
              </tr>
              <tr>
                <td style="padding: 8px 0; font-size: 14px; color: #e8e8f0;">
                  🚀 &nbsp;<strong>Release day alerts</strong>
                  <span style="color: #6b6b80; font-size: 13px; display: block; margin-left: 28px; margin-top: 2px;">
                    On the day of release — where it's still available
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <p style="font-size: 14px; color: #6b6b80; line-height: 1.6; margin: 0;">
        One email per retailer as they go live — no spam, no digests.<br>
        Don't want alerts? <a href="{unsubscribe_url}">Unsubscribe instantly</a>.
      </p>
    """
    return subject, _wrap(content, unsubscribe_url)


# ── 2. Pre-order alert ─────────────────────────────────────────
def preorder_alert(set_name: str, retailer: str, url: str, unsubscribe_url: str) -> tuple[str, str]:
    subject = f"Pre-orders just opened — {set_name} at {retailer}"
    content = f"""
      <p style="margin: 0 0 16px;">{_badge("Pre-order open", "#4A90E2")}</p>
      <h1 style="font-size: 26px; font-weight: 800; color: #e8e8f0; margin: 0 0 8px; line-height: 1.2;">
        {set_name}
      </h1>
      <p style="font-size: 16px; color: #6b6b80; margin: 0 0 24px;">
        Pre-orders just opened at <strong style="color: #e8e8f0;">{retailer}</strong>
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" style="background: #1a1a26; border: 1px solid #4A90E255; border-radius: 8px; margin-bottom: 24px;">
        <tr>
          <td style="padding: 16px 20px;">
            <p style="font-size: 13px; color: #6b6b80; margin: 0 0 4px; text-transform: uppercase; letter-spacing: 1px;">Retailer</p>
            <p style="font-size: 16px; font-weight: 600; color: #e8e8f0; margin: 0;">{retailer}</p>
          </td>
          <td style="padding: 16px 20px; text-align: right;">
            {_badge("Pre-order", "#4A90E2")}
          </td>
        </tr>
      </table>

      {_cta_button("Pre-order now &rarr;", url)}

      <p style="font-size: 13px; color: #6b6b80; margin: 0; line-height: 1.5;">
        Pre-orders can sell out fast — especially for popular sets. We'll alert you again if other
        retailers open pre-orders or stock comes in.
      </p>
    """
    return subject, _wrap(content, unsubscribe_url)


# ── 3. Back in stock alert ─────────────────────────────────────
def restock_alert(set_name: str, retailer: str, url: str, unsubscribe_url: str) -> tuple[str, str]:
    subject = f"{set_name} is back in stock at {retailer}"
    content = f"""
      <p style="margin: 0 0 16px;">{_badge("Back in stock", "#4AE2A0")}</p>
      <h1 style="font-size: 26px; font-weight: 800; color: #e8e8f0; margin: 0 0 8px; line-height: 1.2;">
        {set_name}
      </h1>
      <p style="font-size: 16px; color: #6b6b80; margin: 0 0 24px;">
        Stock just landed at <strong style="color: #e8e8f0;">{retailer}</strong> — it won't last long.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" style="background: #1a1a26; border: 1px solid #4AE2A055; border-radius: 8px; margin-bottom: 24px;">
        <tr>
          <td style="padding: 16px 20px;">
            <p style="font-size: 13px; color: #6b6b80; margin: 0 0 4px; text-transform: uppercase; letter-spacing: 1px;">Retailer</p>
            <p style="font-size: 16px; font-weight: 600; color: #e8e8f0; margin: 0;">{retailer}</p>
          </td>
          <td style="padding: 16px 20px; text-align: right;">
            {_badge("Available", "#4AE2A0")}
          </td>
        </tr>
      </table>

      {_cta_button("Grab it now &rarr;", url)}

      <p style="font-size: 13px; color: #6b6b80; margin: 0; line-height: 1.5;">
        Popular sets can sell out in minutes. We check every few hours — act fast.
      </p>
    """
    return subject, _wrap(content, unsubscribe_url)


# ── 4. Release day alert ───────────────────────────────────────
def release_day_alert(set_name: str, retailers: list[dict], unsubscribe_url: str) -> tuple[str, str]:
    subject = f"{set_name} releases today 🚀"

    status_colours = {
        "available": "#4AE2A0",
        "preorder":  "#4A90E2",
        "soldout":   "#E24A4A",
        "unknown":   "#6b6b80",
    }
    status_labels = {
        "available": "Available",
        "preorder":  "Pre-order",
        "soldout":   "Sold Out",
        "unknown":   "Check Site",
    }

    retailer_rows = ""
    for r in retailers:
        status = r.get("status", "unknown")
        colour = status_colours.get(status, "#6b6b80")
        label  = status_labels.get(status, "Check Site")
        url    = r.get("url", "#")
        name   = r.get("name", "Retailer")
        retailer_rows += f"""
          <tr>
            <td style="padding: 12px 20px; border-bottom: 1px solid #2a2a3a; font-size: 14px; color: #e8e8f0;">
              {name}
            </td>
            <td style="padding: 12px 20px; border-bottom: 1px solid #2a2a3a; text-align: center;">
              {_badge(label, colour)}
            </td>
            <td style="padding: 12px 20px; border-bottom: 1px solid #2a2a3a; text-align: right;">
              <a href="{url}" style="font-size: 13px; color: #FFD700;">Visit &rarr;</a>
            </td>
          </tr>
        """

    content = f"""
      <p style="margin: 0 0 16px;">{_badge("Release Day", "#FFD700")}</p>
      <h1 style="font-size: 26px; font-weight: 800; color: #e8e8f0; margin: 0 0 8px; line-height: 1.2;">
        {set_name}
      </h1>
      <p style="font-size: 16px; color: #6b6b80; margin: 0 0 28px;">
        It's out today — here's where you can still get it.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" style="background: #1a1a26; border: 1px solid #2a2a3a; border-radius: 8px; margin-bottom: 24px;">
        <tr>
          <td style="padding: 12px 20px; border-bottom: 1px solid #2a2a3a;">
            <span style="font-size: 11px; font-weight: 700; color: #FFD700; letter-spacing: 1px; text-transform: uppercase;">Retailer</span>
          </td>
          <td style="padding: 12px 20px; border-bottom: 1px solid #2a2a3a; text-align: center;">
            <span style="font-size: 11px; font-weight: 700; color: #FFD700; letter-spacing: 1px; text-transform: uppercase;">Status</span>
          </td>
          <td style="padding: 12px 20px; border-bottom: 1px solid #2a2a3a; text-align: right;">
            <span style="font-size: 11px; font-weight: 700; color: #FFD700; letter-spacing: 1px; text-transform: uppercase;">Link</span>
          </td>
        </tr>
        {retailer_rows}
      </table>

      <p style="font-size: 13px; color: #6b6b80; margin: 0; line-height: 1.5;">
        We check stock every few hours and will alert you if more stock comes in.
      </p>
    """
    return subject, _wrap(content, unsubscribe_url)
