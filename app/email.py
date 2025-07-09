# app/email.py
import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger(__name__)

def send_email(to_email, subject, html_content):
    """
    Sends an email using SendGrid.
    """
    sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
    from_email = os.environ.get('MAIL_FROM_EMAIL')

    if not sendgrid_api_key or not from_email:
        logger.error("SENDGRID_API_KEY or MAIL_FROM_EMAIL environment variables not set.")
        return False

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        logger.info(f"Email sent to {to_email}, status code: {response.status_code}")
        return response.status_code == 202
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}", exc_info=True)
        return False

def send_password_reset_email(user):
    """
    Generates a password reset token and sends the email to the user.
    """
    token = user.get_reset_password_token()
    from flask import url_for
    
    # The HTML content for the email
    html_content = f"""
        <p>Dear {user.email},</p>
        <p>To reset your password, please click the following link:</p>
        <p><a href="{url_for('reset_password', token=token, _external=True)}">Reset Password</a></p>
        <p>This link will expire in 15 minutes.</p>
        <p>If you did not make this request, please ignore this email.</p>
        <p>Sincerely,<br>The Synapse Finance Team</p>
    """
    return send_email(
        to_email=user.email,
        subject='[Synapse Finance] Reset Your Password',
        html_content=html_content
    )

def send_price_alert_email(user, alert):
    """
    Sends an email to a user about a triggered price alert.
    """
    from flask import url_for
    
    html_content = f"""
        <p>Dear {user.email},</p>
        <p>This is a notification that your price alert for <strong>{alert.symbol}</strong> has been triggered.</p>
        <p>
            Your condition was: Price to be <strong>{alert.condition} ${alert.target_price:.2f}</strong>.
        </p>
        <p>
            You can view the stock on your <a href="{url_for('dashboard', query=alert.symbol, _external=True)}">dashboard</a>.
        </p>
        <p>This alert has now been deactivated.</p>
        <p>Sincerely,<br>The Synapse Finance Team</p>
    """
    return send_email(
        to_email=user.email,
        subject=f'[Synapse Finance] Price Alert Triggered for {alert.symbol}',
        html_content=html_content
    )
