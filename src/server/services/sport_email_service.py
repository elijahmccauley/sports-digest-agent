"""
Simple Email Service for Sports Digest Delivery

A lightweight SMTP service for sending newspapers to yourself.
Just the essentials - no complex templating or multi-user features.
"""

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict

import markdown
from fastmcp.utilities.logging import get_logger
from jinja2 import Environment, FileSystemLoader, select_autoescape


class SportEmailService:
    """Simple email service for sports digest delivery."""

    def __init__(self, email_settings):
        """Initialize with email settings."""
        self.logger = get_logger("EmailService")

        # Handle both dict and EmailSettings object
        if isinstance(email_settings, dict):
            # Dictionary input
            self.server = email_settings.get("server", "localhost")
            self.port = email_settings.get("port", 587)
            self.use_tls = email_settings.get("use_tls", True)
            self.use_ssl = email_settings.get("use_ssl", False)
            self.username = email_settings.get("username", "")
            self.password = email_settings.get("password", "")
            self.from_email = email_settings.get("from_email", "digest@localhost")
            self.from_name = email_settings.get("from_name", "Sports Digest Agent")
        else:
            # EmailSettings object
            self.server = email_settings.server
            self.port = email_settings.port
            self.use_tls = email_settings.use_tls
            self.use_ssl = getattr(email_settings, "use_ssl", False)
            self.username = email_settings.username
            self.password = email_settings.password
            self.from_email = email_settings.from_email
            self.from_name = email_settings.from_name

        # Setup Jinja2 for templates
        template_dir = Path(__file__).parent.parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Add markdown filter
        self.jinja_env.filters["markdown"] = lambda text: (
            markdown.markdown(text) if text else ""
        )

    def send_digest(
        self, digest_data: Dict, subject: str = None, version: int = 1
    ) -> Dict:
        """
        Send sports digest to your personal email.

        Args:
            digest_data: Dict with sports digest content
            subject: Email subject (optional)

        Returns:
            Dict: Success status and details
        """
        try:
            # Create email
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = self.from_email  # Always send to yourself
            msg["Subject"] = (
                subject
                or f"🏀 {digest_data.get('title', 'Your Sports Digest')} - {datetime.now().strftime('%B %d, %Y')}"
            )

            # Create simple text and HTML versions
            text_content = self._create_text_version(digest_data)
            html_content = self._create_html_version(digest_data, version)

            # Attach both versions
            text_part = MIMEText(text_content, "plain", "utf-8")
            html_part = MIMEText(html_content, "html", "utf-8")

            msg.attach(text_part)
            msg.attach(html_part)

            # Send email - handle both SSL and TLS
            if self.use_ssl:
                # Use SSL (port 465)
                server = smtplib.SMTP_SSL(self.server, self.port, timeout=30)
                self.logger.debug(f"Connected via SSL to {self.server}:{self.port}")
            else:
                # Use TLS (port 587)
                server = smtplib.SMTP(self.server, self.port, timeout=30)
                if self.use_tls:
                    server.starttls()
                    self.logger.debug(f"Started TLS on {self.server}:{self.port}")

            # Login and send
            if self.username and self.password:
                server.login(self.username, self.password)
                self.logger.debug("SMTP login successful")

            server.send_message(msg)
            server.quit()

            self.logger.info("Digest sent successfully")
            return {"success": True, "message": "Sports Digest delivered to your email"}

        except Exception as e:
            self.logger.error(f"Failed to send digest: {e}")
            return {"success": False, "error": str(e)}

    def _create_text_version(self, digest_data: Dict) -> str:
        """Create simple text version of sports digest."""
        title = digest_data.get("title", "Your Sports Digest")
        date = datetime.now().strftime("%B %d, %Y")
        sports_sections = digest_data.get("sports_sections", [])

        content = f"{title}\n{date}\n{'=' * len(title)}\n\n"

        for section in sports_sections:
            sport = section.get("sport", "Sport")
            content += f"{sport.upper()}\n{'-' * len(sport)}\n\n"

            if section.get("todays_games"):
                content += "📅 Today's Schedule:\n"
                content += section["todays_games"] + "\n\n"

            if section.get("yesterdays_scores"):
                content += "🏆 Yesterday's Results:\n"
                content += section["yesterdays_scores"] + "\n\n"

            if section.get("news"):
                content += "📰 Latest News:\n"
                content += section["news"] + "\n\n"

            if section.get("odds"):
                content += "💰 Betting Lines:\n"
                content += section["odds"] + "\n\n"

            content += "\n"

        content += f"\n---\nGenerated by Sports Digest Agent on {date}"
        return content

    def _create_html_version(self, digest_data: Dict, version: int = 1) -> str:
        """Create HTML version using enhanced template."""
        template = self.jinja_env.get_template(f"digest_email_v{version}.html")

        return template.render(
            digest_title=digest_data.get("title", "Sports Digest"),
            current_date=datetime.now().strftime("%A, %B %d, %Y"),
            sports_sections=digest_data.get("sports_sections", []),
            user_email=digest_data.get("user_email", ""),
            preferences=digest_data.get("preferences", {}),
        )
        
