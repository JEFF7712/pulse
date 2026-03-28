import smtplib
from email.message import EmailMessage

from pulse.domain.notifications import Notification


class SmtpChannel:
    """Send notifications as plain-text email."""

    def __init__(
        self,
        host: str,
        port: int,
        from_addr: str,
        to_addrs: list[str],
        username: str | None = None,
        password: str | None = None,
        *,
        use_tls: bool = True,
        use_ssl: bool = False,
    ) -> None:
        self._host = host.strip()
        self._port = port
        self._from = from_addr.strip()
        self._to = [a.strip() for a in to_addrs if a.strip()]
        self._username = username.strip() if username else None
        self._password = password
        self._use_tls = use_tls
        self._use_ssl = use_ssl

    def send(self, notification: Notification) -> bool:
        if not self._to:
            return False

        msg = EmailMessage()
        msg["Subject"] = notification.title[:200]
        msg["From"] = self._from
        msg["To"] = ", ".join(self._to)
        msg.set_content(notification.body)

        if self._use_ssl:
            with smtplib.SMTP_SSL(self._host, self._port, timeout=30) as smtp:
                if self._username and self._password is not None:
                    smtp.login(self._username, self._password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
                smtp.ehlo()
                if self._use_tls:
                    smtp.starttls(context=_ssl_context())
                    smtp.ehlo()
                if self._username and self._password is not None:
                    smtp.login(self._username, self._password)
                smtp.send_message(msg)
        return True


def _ssl_context():
    import ssl

    return ssl.create_default_context()
