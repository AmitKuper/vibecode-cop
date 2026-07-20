"""Send game report via email."""

import logging

from agent.reports.base import ReportPlugin

logger = logging.getLogger(__name__)


class EmailReportPlugin(ReportPlugin):
    """Send game report via email (requires SMTP config)."""

    async def generate(self, game_id: str, game_state: dict, game_dir: str) -> dict:
        """Send email report.

        Args:
            game_id: Game identifier
            game_state: Final game state
            game_dir: Path to game memory directory

        Returns:
            Result dict
        """
        try:
            # Check required config
            smtp_host = self.config.get("smtp_host")
            smtp_port = self.config.get("smtp_port", 587)
            sender = self.config.get("from")
            recipient = self.config.get("to")

            if not all([smtp_host, sender, recipient]):
                return {
                    "ok": False,
                    "message": "Missing SMTP configuration (smtp_host, from, to)",
                    "destination": None,
                }

            # Build email content
            winner = game_state.get("winner", "unknown").upper()
            turns = len(game_state.get("move_history", []))
            cop_pos = game_state.get("cop_position")
            thief_pos = game_state.get("thief_position")

            subject = f"Game Report: {game_id} - {winner} Wins"
            body = f"""
Game Report: {game_id}

Result: {winner} WINS

Final State:
- Cop Position: {cop_pos}
- Thief Position: {thief_pos}
- Total Turns: {turns}

Game completed at: {game_state.get('ended_at', 'N/A')}
"""

            # Try to send email
            try:
                import smtplib
                from email.mime.text import MIMEText

                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["From"] = sender
                msg["To"] = recipient

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    if self.config.get("username"):
                        server.login(self.config["username"], self.config.get("password", ""))
                    server.send_message(msg)

                logger.info(f"Email report sent to {recipient}")
                return {
                    "ok": True,
                    "message": f"Report sent to {recipient}",
                    "destination": recipient,
                }

            except ImportError:
                logger.warning("smtplib not available (standard library, should work)")
                return {
                    "ok": False,
                    "message": "Email libraries not available",
                    "destination": None,
                }
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                return {
                    "ok": False,
                    "message": f"SMTP error: {e}",
                    "destination": None,
                }

        except Exception as e:
            logger.error(f"EmailReportPlugin failed: {e}", exc_info=True)
            return {
                "ok": False,
                "message": str(e),
                "destination": None,
            }
